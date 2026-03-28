from dotenv import load_dotenv

from vk_client import VKClient


def check_auth():
    """
    Standalone script to verify VK API tokens and basic search capabilities.
    """
    load_dotenv()

    print("--- Starting VK API Auth Verification ---")

    try:
        # Initialize client
        # This will fail if VK_USER_TOKEN or VK_GROUP_TOKEN are missing in .env
        client = VKClient()
        print("[OK] Environment variables loaded and VKClient initialized.")

        # 1. Verify Group Token
        print("\nVerifying Community (Group) API...")
        try:
            # groups.getById without params returns info about the group the token belongs to
            group_info = client.group_api.groups.getById()
            group_name = group_info[0].get("name")
            group_id_api = group_info[0].get("id")
            print(
                f"[OK] Group Token verified. Group: '{group_name}' (ID: {group_id_api})"
            )
        except Exception as e:
            print(f"[FAIL] Group Token verification failed: {e}")

        # 2. Verify User Token
        print("\nVerifying User Search API...")
        try:
            # users.get without params returns info about the user the token belongs to
            user_info = client.user_api.users.get()
            user_name = f"{user_info[0].get('first_name')} {user_info[0].get('last_name')}"
            print(f"[OK] User Token verified for user: {user_name}")

            # Perform a dummy search to confirm search capabilities
            # Searching for a famous person to ensure results are found
            search_results = client.search_users(q="Dmitry Medvedev", count=5)
            results_count = search_results.get("count", 0)
            print("[OK] User Search API connectivity: OK")
            print(
                f"     Found {results_count} total results for 'Dmitry Medvedev'."
            )

        except Exception as e:
            print(f"[FAIL] User Token verification or search failed: {e}")

    except ValueError as e:
        print(f"[CRITICAL] Configuration Error: {e}")
        print(
            "Please ensure your .env file contains VK_USER_TOKEN and VK_GROUP_TOKEN."
        )
    except Exception as e:
        print(f"[CRITICAL] Unexpected error during initialization: {e}")


if __name__ == "__main__":
    check_auth()
