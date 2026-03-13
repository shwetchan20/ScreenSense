# ScreenSense Submission Checklist

## 1. Local Product Readiness
- [x] Continuous capture + frame diff loop is stable
- [x] Interrupt policy implemented (confidence, idle gate, cooldown, dedupe)
- [x] Vision error handling with backoff (no hard crash on API errors)
- [x] Gemini rate guard implemented (min interval + calls/min cap)
- [x] Audit logging enabled (`runtime/audit.log.jsonl`)
- [x] Focus controls implemented (`FOCUS_MODE`, `APP_TITLE_BLOCKLIST`)
- [ ] 2-4 hour stability run completed without critical failure

## 2. Action Safety (HITL)
- [x] Product modes implemented (`observe`, `ask`, `allowlisted_auto`)
- [x] Action policy implemented (allowlist + risk gate)
- [x] Action preview before execution
- [x] Action execution result includes verification status
- [ ] At least 1 concrete safe action workflow validated end-to-end in daily use

## 3. Cloud Compliance (Mandatory)
- [ ] Billing-enabled GCP project available
- [ ] Required APIs enabled (`Cloud Run`, `Firestore`, `Secret Manager`)
- [ ] Backend hosted on Google Cloud (Cloud Run)
- [ ] At least one Google Cloud service integrated (Firestore)
- [x] Desktop client connected to cloud backend for inference path

## 4. Repository Quality
- [x] Tests passing locally
- [x] Secrets excluded from git (`.env` ignored)
- [ ] Public repository prepared for judges
- [ ] README includes full reproducible spin-up instructions
- [x] Architecture diagram added to repo

## 5. Submission Assets
- [ ] <4 minute demo video (real multimodal flow, no mockups)
- [ ] Google Cloud proof video (deployment/service running)
- [ ] Project write-up (features, stack, data sources, learnings)
- [ ] Final checklist review before submission

## 6. Nice-to-Have (Post-Core)
- [ ] Human-like voice provider (`edge-tts`) with persona styles
- [ ] Mobile remote approval channel (push + approve/deny)

## 7. UI/UX Layer
- [x] Command-center dashboard implemented
- [x] Ghost + Notify state visualized
- [ ] System tray integration
