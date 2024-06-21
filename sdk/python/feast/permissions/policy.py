from abc import ABC, abstractmethod

from feast.permissions.role_manager import RoleManager


class Policy(ABC):
    """
    An abstract class to ensure that the current user matches the configured security policies.
    """

    @abstractmethod
    def validate_user(self, user: str, **kwargs) -> tuple[bool, str]:
        """
        Converts data source config in protobuf spec to a DataSource class object.

        Args:
            data_source: A protobuf representation of a DataSource.

        Returns:
            A DataSource class object.

        Raises:
            ValueError: The type of DataSource could not be identified.
        """
        raise NotImplementedError


class RoleBasedPolicy(Policy):
    """
    An Policy class where the user roles must be enforced to grant access to the requested action.
    All the configured roles must be granted to the current user in order to allow the execution.

    The `role_manager` keywork argument must be present in the `kwargs` optional key-value arguments.
    """

    def __init__(
        self,
        roles: list[str],
    ):
        self.roles = roles

    def get_roles(self) -> list[str]:
        return self.roles

    def validate_user(self, user: str, **kwargs) -> tuple[bool, str]:
        if "role_manager" not in kwargs:
            raise ValueError("Missing keywork argument 'role_manager'")
        if not isinstance(kwargs["role_manager"], RoleManager):
            raise ValueError(
                f"The keywork argument 'role_manager' is not of the expected type {RoleManager.__name__}"
            )
        rm = kwargs.get("role_manager")
        if isinstance(rm, RoleManager):
            result = rm.has_roles_for_user(user, self.roles)
        explain = "" if result else f"Requires roles {self.roles}"
        return (result, explain)


def allow_all(self, user: str, **kwargs) -> tuple[bool, str]:
    return True, ""


"""
A `Policy` instance to allow execution of any action to each user
"""
AllowAll = type("AllowAll", (Policy,), {Policy.validate_user.__name__: allow_all})()
