# AGENTS.md

Use YAGNI: make the smallest change that preserves the required behavior.

## Environment Files

Real `.env*` files (not placeholder examples) are dotenvx-encrypted source of truth and are committed. Never commit `.env.keys` or `DOTENV_PRIVATE_KEY`; Kristian's machine keeps the one shared private key at `~/.config/dotenvx/.env.keys` and its public key at `~/.config/dotenvx/public.env`. Reuse that keypair for every env file and use `dotenvx run -- <command>` or `dotenvx set KEY value` instead of plaintext secrets.
