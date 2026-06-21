# Security

Do not commit OAuth client secrets, refresh tokens, reporter tokens, private
HTTPS keys, or Android device credentials.

Report vulnerabilities through GitHub's private security advisory feature for
this repository. Do not open a public issue containing credentials or an
unpatched vulnerability.

The local reporter token authorizes current-track reports, transport commands,
and rating changes. Expose the HTTP server only through a private network or an
authenticated HTTPS reverse proxy.
