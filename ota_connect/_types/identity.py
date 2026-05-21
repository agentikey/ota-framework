# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

IdentityRef = str  # canonical form; parsed at framework boundary
# Accepted string forms (prefix-driven for deterministic parsing):
#   "handle:@<name>"         e.g. "handle:@jamie"
#                            → looked up via relationships.md or locally verified
#                              system rosters; resolved per bound adapter
#   "mailto:<address>"       e.g. "mailto:jamie@coachfirm.com"
#                            → direct routing via SMTP or email-bound enterprise channels
#   "raw:<adapter>:<id>"     e.g. "raw:slack:U02ABCD"
#                            → opaque escape-hatch bypassing identity resolution;
#                              framework warns on use
