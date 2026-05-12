#!/usr/bin/env node

import { createCipheriv, randomBytes, scryptSync } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";

const REPO = resolve(import.meta.dirname, "..");
const OUT = process.env.OPENCLAW_SECRETS_OUT ?? join(REPO, "secrets/openclaw-secrets.enc.json");

function readPassphrase() {
  if (process.env.OPENCLAW_SECRETS_PASSPHRASE) return process.env.OPENCLAW_SECRETS_PASSPHRASE;
  if (process.env.OPENCLAW_SECRETS_PASSPHRASE_FILE) {
    return readFileSync(process.env.OPENCLAW_SECRETS_PASSPHRASE_FILE, "utf8").trim();
  }
  throw new Error(
    "Set OPENCLAW_SECRETS_PASSPHRASE or OPENCLAW_SECRETS_PASSPHRASE_FILE before exporting.",
  );
}

function fileEntry(label, filePath) {
  if (!existsSync(filePath)) return null;
  const st = statSync(filePath);
  if (!st.isFile()) return null;
  return {
    label,
    path: filePath,
    mode: st.mode & 0o777,
    content: readFileSync(filePath, "utf8"),
  };
}

const files = [
  fileEntry("OpenClaw live config", join(homedir(), ".openclaw/openclaw.json")),
  fileEntry("Cognee env", join(REPO, ".env.cognee")),
  fileEntry("Repo env", join(REPO, ".env")),
  fileEntry("Repo local env", join(REPO, ".env.local")),
].filter(Boolean);

if (files.length === 0) {
  throw new Error("No known OpenClaw/Cognee secret files found to export.");
}

const payload = JSON.stringify(
  {
    version: 1,
    exportedAt: new Date().toISOString(),
    repo: REPO,
    files,
  },
  null,
  2,
);

const salt = randomBytes(16);
const iv = randomBytes(12);
const key = scryptSync(readPassphrase(), salt, 32);
const cipher = createCipheriv("aes-256-gcm", key, iv);
const ciphertext = Buffer.concat([cipher.update(payload, "utf8"), cipher.final()]);
const tag = cipher.getAuthTag();

const bundle = {
  schema: "companion-openclaw-secrets/aes-256-gcm+scrypt/v1",
  createdAt: new Date().toISOString(),
  kdf: "scrypt",
  cipher: "aes-256-gcm",
  salt: salt.toString("base64"),
  iv: iv.toString("base64"),
  tag: tag.toString("base64"),
  ciphertext: ciphertext.toString("base64"),
  contains: files.map((f) => f.label),
};

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, `${JSON.stringify(bundle, null, 2)}\n`, { mode: 0o600 });
console.log(`Encrypted ${files.length} secret file(s) to ${OUT}`);
console.log("Keep the passphrase outside git; it is required to restore this bundle.");
