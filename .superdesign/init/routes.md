# CoolProof routes

Current deployed static routes:

| URL | Source | Purpose |
|---|---|---|
| `/` | `frontend/index.html` | Public product/demo landing surface |
| `/docs` | FastAPI | Swagger UI |
| `/redoc` | FastAPI | ReDoc |
| `/openapi.json` | FastAPI | API contract |

Planned authenticated frontend routes from point 18:

| URL | Surface |
|---|---|
| `/portfolio` | City budget, projects, and impact |
| `/zones/:zoneId` | FortyGuard heat evidence |
| `/plans/:runId` | Agent workflow and intervention alternatives |
| `/optimize` | Constraints and allocation result |
| `/verify/:reportId` | Predicted versus measured impact |
| `/ask` | Narrow command interface for governed changes |
