# Roadmap

## V1 — Complete (Private Family Use)

Everything needed to go from photos to a PDF storybook, delivered by email.

- [x] iPhone Share Sheet Shortcut sends one JSON POST to FastAPI
- [x] Immediate `processing` response (Shortcut never times out)
- [x] Async background job runner with on-disk job store
- [x] Image preprocessing and base64 media staging
- [x] OpenAI Vision descriptions of family photos
- [x] Story generation: memories → magical children's adventure (ages 5–7)
- [x] Pydantic validation + critic/self-check retry loop
- [x] WeasyPrint PDF rendering via Jinja2 template
- [x] S3 upload with presigned download URL
- [x] SES email delivery of finished PDF
- [x] Failure notifications via email and logs
- [x] Docker image with all WeasyPrint system deps
- [x] Docker Compose for single-command deploy
- [x] API key auth
- [x] Mock-AI mode for dev/test without OpenAI spend

### V1 Non-Goals

- No public web app or consumer SaaS
- No microservices or multi-container orchestration
- No KDP/publishing automation — manual export only
- No advanced user accounts or multi-tenant
- No Terraform/CDK infrastructure-as-code (overbuild for a single-instance deploy)

---

## V1.1 — Reliability & Observability

Harden what exists before adding features.

- [ ] **Retry with back-off** on transient OpenAI and AWS errors
- [ ] **Idempotency guard** — reject or deduplicate duplicate Shortcut submissions
- [ ] **Job expiry / cleanup** — purge stale work dirs and old job records
- [ ] **Structured logging** — JSON logs with job ID correlation for easy grep
- [ ] **Health endpoint depth** — `/healthz` checks disk, S3 reachability, and OpenAI key validity
- [ ] **Timeout budgets** — per-image vision timeout, total job deadline, hard kill
- [ ] **Basic alerting** — failure-count threshold triggers admin email digest
- [ ] **Graceful shutdown** — finish in-flight job before container stops

---

## V1.2 — Parent Review & Control

Give the parent a chance to see and approve before the book is final.

- [ ] **Draft preview** — generate low-res preview images or a watermarked draft PDF
- [ ] **Approval flow** — email contains "approve" / "reject + note" links; approved → final render + delivery
- [ ] **Photo selection** — let parent reorder or exclude photos before generation (Shortcut UI or a simple one-page web form)
- [ ] **Child name / age input** — personalize the story; stored per-request, not in a user DB

---

## V2 — Better Book Design

Improve the look and feel of the PDF output.

- [ ] **Page layout engine** — support full-bleed images, text-over-image, and varied page templates
- [ ] **Typography** — curated child-friendly font pairings; configurable in settings
- [ ] **Cover page** — auto-generated cover with title, child's name, and a hero image
- [ ] **Illustration style prompt** — optional AI-generated illustration alongside each photo
- [ ] **Spreads** — two-page spread support for landscape photos
- [ ] **CSS themes** — swap visual style without changing code (e.g., watercolor, storybook, comic)

---

## V2.1 — Print-on-Demand Research (Manual Export Only)

> V1 does **not** automate publishing. This phase is research + manual workflow.

- [ ] **PDF/X compliance** — validate output meets print-ready spec (bleed, trim, color profile)
- [ ] **Page-count constraints** — enforce minimum/maximum page counts for common POD services
- [ ] **Spine width calculator** — compute spine from page count + paper stock
- [ ] **Export instructions doc** — step-by-step guide: download PDF → upload to Lulu / Blurb / KDP manually
- [ ] **ISBN / barcode placeholder** — reserve back-cover space if needed
- [ ] **Sample order checklist** — what to verify in a physical proof copy

---

## V3 — Productization

Only pursue after the family product is solid and genuinely useful.

- [ ] **Multi-user support** — lightweight auth (magic link or OAuth), per-user job history
- [ ] **Usage metering** — track OpenAI token spend per job; surface cost to admin
- [ ] **Rate limiting** — per-user and global request caps
- [ ] **Stripe integration** — charge per book or subscription; webhook for payment confirmation
- [ ] **Terms of service / privacy policy** — required before any external users
- [ ] **Landing page** — simple static site explaining the product
- [ ] **Waitlist / invite system** — controlled rollout

---

## Ongoing — AI Quality

Continuous improvement, not a gated phase.

- [ ] **Prompt versioning** — track prompt text in version control; A/B test new prompts against saved outputs
- [ ] **Eval suite** — golden-set of photo batches with expected story qualities; score automatically
- [ ] **Model upgrades** — test new OpenAI models on the eval suite before switching
- [ ] **Vision prompt tuning** — reduce hallucination, improve scene detail, handle edge cases (blurry, dark, screenshots)
- [ ] **Story tone controls** — configurable tone (funny, adventurous, calm bedtime) per request
- [ ] **Critic prompt iteration** — tighten the self-check to catch repetition, age-inappropriateness, and pacing issues
- [ ] **Cost optimization** — batch vision calls, use cheaper models for non-critical steps, cache repeated descriptions
