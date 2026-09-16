# Security policy

Please report vulnerabilities privately through GitHub Security Advisories for
`Danw33/ha-equilab`. Do not open a public issue containing credentials, tokens,
account identifiers, training details, or location data.

Only the latest released version receives security fixes. This library is unofficial,
uses an undocumented upstream API, and must only be used with data the caller is
authorised to access.

This is an unofficial community project. Do not report integration
vulnerabilities to Eqilab support unless they independently affect a Equilab
product/service and you follow the vendor's own responsible disclosure process.

Only the latest released integration version will receive security fixes while
the project is pre-1.0. No version has been released yet.

## Scope and guarantees

The integration is unofficial and uses an undocumented cloud interface that may change without notice. It
stores a refresh token in the Home Assistant config entry but does not retain the submitted password. Review
Home Assistant backups and diagnostics before sharing them, because they may contain sensitive configuration
or riding metadata.
