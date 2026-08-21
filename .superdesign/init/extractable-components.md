# Extractable components

## AppShell
- Source: planned Vercel app shell
- Category: layout
- Description: Authenticated navigation shell with organization switcher and route navigation
- Extractable props: activeRoute, organizationName, userEmail

## StatusCard
- Source: `frontend/index.html`
- Category: basic
- Description: Operational health or metric card with status dot and value
- Extractable props: label, value, state, detail

## WorkflowTimeline
- Source: planned `/plans/:runId`
- Category: basic
- Description: Five-stage agent execution timeline
- Extractable props: activeStage, completedStages, failedStage

## EvidenceCitation
- Source: planned `/zones/:zoneId` and `/plans/:runId`
- Category: basic
- Description: Cited document excerpt with page/source metadata
- Extractable props: title, page, excerpt, href
