# Ownership and research authorization

Every private root record references an ownership scope, which can belong to one durable user. A validated auth session selects one of that user's workspaces. Existing owner predicates and parent authorization continue to protect histories, snapshots, saved risk/ML/model/artifacts, documents/chunks, investigations/evidence, optimization/studies/scenarios and governance. Random object IDs are references, never proof of access. Child artifacts inherit authorized parent access. Lost legacy owners remain unclaimed; no automatic reassignment occurs.

| Role | Permitted authority |
| --- | --- |
| USER | Own active-workspace portfolio/data/research/optimization/investigation and account controls; submit/retire own research proposals. |
| RESEARCH_REVIEWER | In addition to own data, read and review only explicitly assigned model evidence. Cannot validate/approve their own model. |
| RESEARCH_ADMIN | Manage review assignments for models in their own administered workspace; no blanket access to other users' private data. |
| PLATFORM_ADMIN | Manage account status/roles and operational controls; no automatic financial-document, model evidence or broker-credential access. |

All accounts begin with USER only. Role changes require explicit operator or authorized platform-administrator action and a security event. Suspension revokes sessions. Frontend visibility is convenience; backend checks are authoritative. Global administrator status cannot select another user's workspace or bypass owner predicates.

Model assignments identify a specific active reviewer UUID, not an arbitrary account or whole portfolio. Only an explicitly provisioned RESEARCH_ADMIN owning the workspace can assign an active RESEARCH_REVIEWER. The creator cannot be assigned to independently review their own model, even with multiple roles or workspaces. Validation, approval and rejection require a different assigned reviewer. Owners can submit for review or retire; the server returns permitted transitions for that actor. An assigned reviewer can inspect the linked model's structured evidence and review events without acquiring general access to its source portfolio, original private PDFs, arbitrary artifacts or other models. Assignment revocation/role removal takes effect on subsequent requests.

Phase 5's numerical/source/reproduction gates, eight substantive assessments and methodology_research-only approval scope remain. New review events identify the durable reviewer and auth-session UUID; older session-only evidence is preserved rather than relabeled. Low QLIKE never grants approval. The legacy champion endpoint additionally requires research-admin authority and a currently evidenced independently approved forecast source for authenticated accounts. Original explicitly local guest workflows remain compatible; they are not available as production authorization.

Agents have no role-assignment, workspace-claim, credential, governance-registration/review or champion-write tools. No new shell/SQL/arbitrary URL/file/trade capabilities exist. Operator maintenance modules are not registered agent tools. The platform remains read-only toward brokerage accounts.

Current local controls do not establish regulatory certification or a complete enterprise review program. Independent reviewer identity can now be demonstrated, but operational provisioning, external identity verification, reviewer competence and real-market validity require separate evidence and process.
