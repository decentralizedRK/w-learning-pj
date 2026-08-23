"""Generate fresh Kite API access token from request token."""

import re
from pathlib import Path

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging
from config.settings import settings


def main() -> None:
    setup_logging()

    if not settings.kite_api_key or not settings.kite_api_secret:
        print("Error: QOS_KITE_API_KEY and QOS_KITE_API_SECRET must be set in .env")
        return

    broker = ZerodhaBroker()
    login_url = broker.generate_login_url()

    print("\n" + "=" * 80)
    print("KITE API TOKEN GENERATION")
    print("=" * 80)
    print(f"\n1. Visit this URL in your browser:\n   {login_url}\n")
    print("2. Log in with your Zerodha credentials")
    print("3. You'll be redirected to a callback URL")
    print("4. Copy the full callback URL and paste it below\n")

    callback = input("Paste callback URL: ").strip()

    match = re.search(r"request_token=([a-zA-Z0-9]+)", callback)
    if not match:
        print("Error: Could not find request_token in callback URL")
        print("Expected format: https://...?request_token=ABC123...")
        return

    request_token = match.group(1)
    print(f"\nRequest token extracted: {request_token}")

    try:
        broker.generate_session(request_token)
        print("\n✅ Session created successfully!")
        print(f"Access token: {broker._get_kite().access_token}\n")

        print("Add this to your .env file:")
        print(f"QOS_KITE_ACCESS_TOKEN={broker._get_kite().access_token}\n")

        env_file = Path(".env")
        if env_file.exists():
            content = env_file.read_text()
            if "QOS_KITE_ACCESS_TOKEN" in content:
                content = re.sub(
                    r"QOS_KITE_ACCESS_TOKEN=.*",
                    f"QOS_KITE_ACCESS_TOKEN={broker._get_kite().access_token}",
                    content,
                )
            else:
                content += f"\nQOS_KITE_ACCESS_TOKEN={broker._get_kite().access_token}\n"
            env_file.write_text(content)
            print("✅ Updated .env file")
        else:
            print("⚠️  .env file not found, create it with the token above")

        print("\n" + "=" * 80)
        print("Now the screener/backtest workflows can use Kite API data!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"Error: {e}")
        print("Check that your API key/secret are correct")


if __name__ == "__main__":
    main()
