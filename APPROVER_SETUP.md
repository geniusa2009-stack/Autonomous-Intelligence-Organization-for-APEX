# Approver setup

A guide becomes FINAL only through an authenticated human approval. This page explains how approvers are created and
how their decisions are recorded. Nothing here may be weakened for convenience. In particular, a typed name is never
accepted as identity.

## 1. Create an approver (once per person)

The approver runs this on the APEX machine:

```
apex-one auth add-approver "<full name>"
```

- **Output:** a token beginning `apx_`, **shown once**. Store it in a password manager immediately. It cannot be shown again.
- **Storage:** APEX keeps only the token's SHA-256 hash, in `<APEX home>/var/auth/approvers.json` (file mode 600, outside git). Nobody, Claude included, can recover the token from it.
- **Ledger:** creating an approver is itself recorded in the approval ledger.
- **One active token per name.** To rotate, revoke first (section 4).

## 2. Using the credential

Hand the token to commands through the environment, never on a shared screen and never in a file in the repository:

```
export APEX_APPROVER_TOKEN=<token>          # in your own shell only
```

For the local API, send `Authorization: Bearer <token>` instead. The API listens on 127.0.0.1 only.

## 3. Permissions (scope)

- **Role:** a token carries one role, `release_approver`.
- **What it can do:** approve or reject a release candidate, and nothing else. It cannot create approvers, change routing, import brands or confirm facts.
- **Who the approver is:** the identity comes from the token alone. Passing `--by "<name>"` only restates who you are; a different name is rejected as **forged**.
- **When it applies:** an approval only works on a job that is waiting at RELEASE_CANDIDATE.

## 4. Revoke a credential

```
apex-one auth revoke "<full name>"
```

Revocation takes effect immediately and is recorded in the ledger. To rotate a token, revoke it, then run
`add-approver` again with the same name. List approvers (never their tokens) with `apex-one auth list`.

## 5. How an approval is bound to the artifact

1. Open and review `final.pdf` of the job; its path is printed by `apex-one inspect <job>`.
2. Compute its fingerprint: `sha256sum <path>/final.pdf`. The job's pause message also prints it.
3. Approve exactly those bytes:
   ```
   APEX_APPROVER_TOKEN=<token> apex-one approve <job_id> --artifact-sha256 <sha256 you computed> --notes "<comment>"
   ```

The ledger entry records:
- who (the token's approver id and name);
- which job;
- when;
- the SHA-256 of `final.pdf` and `final.html`;
- the decision;
- your comment.

If the file changed since you computed the hash, the approval is **refused**. Afterwards the job will not become
FINAL, and `apex-one release export` will not export it, if the PDF no longer matches the approved hash. A rejection
(`apex-one reject <job_id> --notes "<why>"`) is recorded the same way, with the artifact hashes.

## 6. Check the audit history

```
apex-one auth history                 # every ledger entry: approvers created/revoked, every release decision
apex-one auth history --job <job_id>  # one job's decisions, with the approved final.pdf hash
apex-one auth verify-ledger           # proves no entry was edited, deleted or reordered (hash chain)
apex-one release verify <job_id>      # proves the FINAL artifact is byte-identical to what was approved
```

## Done when

`apex-one release check` no longer lists `AUTHORIZED_APPROVER_CONFIGURED`. That requires at least one active
approver and an intact ledger.
