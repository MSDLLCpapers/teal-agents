import msal


class AzureAppToken:

    def get_azure_app_token(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        scope: list[str]
    ):
        try:
            authority = f"https://login.microsoftonline.com/{tenant_id}"

            app = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=client_secret
            )

            result = app.acquire_token_for_client(scopes=scope)

            if "access_token" in result:
                access_token = result["access_token"]
                return access_token
            else:
                print(result.get("error"))
                print(result.get("error_description"))
                return None
        except Exception as e:
            print(e)
            return None
