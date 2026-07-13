#!/usr/bin/env node

import { createDecipheriv, scryptSync } from "node:crypto";
import { chmodSync, copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const REPO = resolve(import.meta.dirname, "..");
const IN = process.env.OPENCLAW_SECRETS_IN ?? join(REPO, "secrets/openclaw-secrets.enc.json");

function readPassphrase() {
  if (process.env.OPENCLAW_SECRETS_PASSPHRASE) return process.env.OPENCLAW_SECRETS_PASSPHRASE;
  if (process.env.OPENCLAW_SECRETS_PASSPHRASE_FILE) {
    return readFileSync(process.env.OPENCLAW_SECRETS_PASSPHRASE_FILE, "utf8").trim();
  }
  throw new Error(
    "Set OPENCLAW_SECRETS_PASSPHRASE or OPENCLAW_SECRETS_PASSPHRASE_FILE before importing.",
  );
}

const bundle = JSON.parse(readFileSync(IN, "utf8"));
const supportedSchemas = new Set([
  "albert-openclaw-secrets/aes-256-gcm+scrypt/v1",
  "companion-openclaw-secrets/aes-256-gcm+scrypt/v1",
]);
if (!supportedSchemas.has(bundle.schema)) {
  throw new Error(`Unsupported secrets bundle schema: ${bundle.schema}`);
}

const key = scryptSync(readPassphrase(), Buffer.from(bundle.salt, "base64"), 32);
const decipher = createDecipheriv(
  "aes-256-gcm",
  key,
  Buffer.from(bundle.iv, "base64"),
);
decipher.setAuthTag(Buffer.from(bundle.tag, "base64"));

const plaintext = Buffer.concat([
  decipher.update(Buffer.from(bundle.ciphertext, "base64")),
  decipher.final(),
]).toString("utf8");

const payload = JSON.parse(plaintext);
for (const file of payload.files ?? []) {
  const target = file.path;
  mkdirSync(dirname(target), { recursive: true });
  if (existsSync(target)) {
    const backup = `${target}.backup-${new Date().toISOString().replaceAll(":", "-")}`;
    copyFileSync(target, backup);
    console.log(`Backed up existing ${target} -> ${backup}`);
  }
  writeFileSync(target, file.content, { mode: file.mode ?? 0o600 });
  chmodSync(target, file.mode ?? 0o600);
  console.log(`Restored ${file.label}: ${target}`);
}

console.log("Secrets import complete. Run npm run hermes:migrate, then restart Hermes after importing.");
