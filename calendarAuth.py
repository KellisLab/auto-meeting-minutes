from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "263334656736-2k5n7lbpkbrlnpm5pma7lab7e9mg6ju9.apps.googleusercontent.com",
            "client_secret": "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",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["https://your-authorized-uri.com/oauth2callback"]
        }
    },
    scopes=["https://www.googleapis.com/auth/calendar"]
)

creds = flow.run_local_server(redirect_uri="https://your-authorized-uri.com/oauth2callback")
