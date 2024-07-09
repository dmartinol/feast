import logging
import os
from unittest.mock import Mock

import jwt
from dotenv import load_dotenv
from fastapi import Request
from fastapi.security import OAuth2AuthorizationCodeBearer
from jwt import PyJWKClient
from starlette.authentication import (
    AuthenticationError,
)

from feast.permissions.auth.token_parser import TokenParser

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OidcTokenParser(TokenParser):
    """
    A `TokenParser` to use an OIDC server to retrieve the user details.
    # TODO RBAC: use auth configuration instead
    Server settings are retrieved fro these environment variables:
    - `OIDC_SERVER_URL`
    - `REALM`
    - `CLIENT_ID`
    """

    def __init__(self):
        # TODO RBAC: use auth configuration instead
        load_dotenv("./.env")

        self._OIDC_SERVER_URL = os.getenv("OIDC_SERVER_URL")
        self._REALM = os.getenv("REALM")
        self._CLIENT_ID = os.getenv("CLIENT_ID")

    async def _validate_token(self, access_token: str):
        """
        Validate the token extracted from the headrer of the user request against the OAuth2 server.
        """
        # FastAPI's OAuth2AuthorizationCodeBearer requires a Request type but actually uses only the headers field
        # https://github.com/tiangolo/fastapi/blob/eca465f4c96acc5f6a22e92fd2211675ca8a20c8/fastapi/security/oauth2.py#L380
        request = Mock(spec=Request)
        request.headers = {"Authorization": f"Bearer {access_token}"}

        oauth_2_scheme = OAuth2AuthorizationCodeBearer(
            tokenUrl=f"{self._OIDC_SERVER_URL}/realms/{self._REALM}/protocol/openid-connect/token",
            authorizationUrl=f"{self._OIDC_SERVER_URL}/realms/{self._REALM}/protocol/openid-connect/auth",
            refreshUrl=f"{self._OIDC_SERVER_URL}/realms/{self._REALM}/protocol/openid-connect/token",
        )

        await oauth_2_scheme(request=request)

    async def user_details_from_access_token(
        self, access_token: str, **kwargs
    ) -> tuple[str, list[str]]:
        """
        Validate the access token then decode it to extract the user credential and roles.

        Returns:
            str: Current user.
            list[str]: Roles associated to the user.

        Raises:
            AuthenticationError if any error happens.
        """

        await self._validate_token(access_token)
        logger.info("Validated token")

        url = f"{self._OIDC_SERVER_URL}/realms/{self._REALM}/protocol/openid-connect/certs"
        optional_custom_headers = {"User-agent": "custom-user-agent"}
        jwks_client = PyJWKClient(url, headers=optional_custom_headers)

        try:
            signing_key = jwks_client.get_signing_key_from_jwt(access_token)
            data = jwt.decode(
                access_token,
                signing_key.key,
                algorithms=["RS256"],
                audience="account",
                options={"verify_exp": True},
            )

            if "preferred_username" not in data:
                raise AuthenticationError(
                    "Missing preferred_username field in access token."
                )
            current_user = data["preferred_username"]

            if "resource_access" not in data:
                raise AuthenticationError(
                    "Missing resource_access field in access token."
                )
            if self._CLIENT_ID not in data["resource_access"]:
                raise AuthenticationError(
                    f"Missing resource_access.{self._CLIENT_ID} field in access token."
                )
            if "roles" not in data["resource_access"][self._CLIENT_ID]:
                raise AuthenticationError(
                    f"Missing resource_access.{self._CLIENT_ID}.roles field in access token."
                )
            roles = data["resource_access"][self._CLIENT_ID]["roles"]
            logger.info(f"Extracted user {current_user} and roles {roles}")
            return (current_user, roles)
        except jwt.exceptions.InvalidTokenError:
            raise AuthenticationError("Invalid token.")