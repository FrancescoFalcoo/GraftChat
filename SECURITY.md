# Security

GraftChat runs on your own computer and holds your OpenRouter API key, so security reports
are welcome and taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead: on this
repository, open the **Security** tab and choose **Report a vulnerability**. Only the
maintainer sees the report.

Include what you found, how to reproduce it, and what an attacker could do with it. You will
get an answer as soon as possible; this is a personal project, so allow a few days.

## Supported versions

Only the latest release and the `main` branch receive fixes.

## How the app protects you today

- **Local only.** The server listens on `127.0.0.1`, so other computers cannot reach it.
- **No other website can use it.** Requests whose `Host` is not `127.0.0.1`, `localhost` or
  `::1` are refused (DNS rebinding), and so are requests that change something when they come
  from another website (`Origin`, `Sec-Fetch-Site`). Both get `403 not_local`.
- **Your key stays on disk.** It is saved in `~/.graftchat/settings.json`, outside the
  repository, and is sent only to OpenRouter. The API never returns it: the interface sees
  only its last four characters.
- **Attachments cannot run.** Documents are served only as downloads, never rendered by the
  browser; images are accepted only when their bytes are PNG, JPEG, GIF or WebP.
- **No third parties.** No analytics, and no external fonts or scripts in the interface.

## Out of scope

- Anyone with access to your user account on the computer can read `~/.graftchat/`: protect
  your computer as you would for any local app.
- What OpenRouter and the model providers do with the messages you send is governed by their
  policies; see the privacy settings of your OpenRouter account.
