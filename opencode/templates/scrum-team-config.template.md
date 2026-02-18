# Scrum Team Config

## App Identity

- **Name**: <your-app-name>
- **Description**: <brief description of what the app does>

## Tech Stack

- **Backend Framework**: <e.g., Quarkus, Spring Boot, Express, Django>
- **Frontend Framework**: <e.g., React 18+ with TypeScript, Vue 3, Next.js>
- **Database**: <e.g., PostgreSQL, MySQL, MongoDB>
- **Migration Tool**: <e.g., Flyway, Liquibase, Prisma, Alembic>
- **Storage**: <e.g., MinIO, S3, local filesystem>
- **Auth**: <e.g., JWT-based, OAuth2, session-based>
- **Build Tool**: <e.g., Maven, Gradle, npm, pnpm>
- **API Pattern**: <e.g., REST with JAX-RS, REST with Express, GraphQL>

## Ports & URLs

- **Frontend Port**: <e.g., 3000>
- **Backend Port**: <e.g., 8070>
- **Dev Domain**: <e.g., https://localhost:3000/>

## Source Paths — Backend

- **Resources/Controllers**: <e.g., src/main/java/com/example/resource/>
- **Entities/Models**: <e.g., src/main/java/com/example/entity/>
- **Services**: <e.g., src/main/java/com/example/service/>
- **DTOs**: <e.g., src/main/java/com/example/dto/>
- **Migrations**: <e.g., src/main/resources/db/migration/>
- **Tests**: <e.g., src/test/>

## Source Paths — Frontend

- **Pages**: <e.g., src/pages/>
- **Workspace Pages**: <e.g., src/pages/workspace/>
- **Components**: <e.g., src/components/>
- **Services (API calls)**: <e.g., src/services/>
- **Types**: <e.g., src/types/>
- **Router**: <e.g., src/router.tsx>

## Source Paths — Testing

- **Test Cases (manual)**: <e.g., docs/e2e-testcases/>
- **Feature Docs**: <e.g., docs/features/>
- **E2E Tests**: <e.g., e2e/tests/>
- **Fixtures**: <e.g., e2e/fixtures/>
- **Page Objects**: <e.g., e2e/pages/>
- **Auth Fixture**: <e.g., e2e/fixtures/auth.fixture.ts>
- **Playwright Config**: <e.g., e2e/playwright.config.ts>

## Commands

- **Start DB**: <e.g., docker compose up -d postgres>
- **Start Storage**: <e.g., docker compose up -d minio>
- **Start Backend**: <e.g., ./mvnw quarkus:dev>
- **Start Frontend**: <e.g., cd src/main/webapp && npm run dev>
- **Compile Backend**: <e.g., ./mvnw compile>
- **Compile Frontend**: <e.g., cd src/main/webapp && npx tsc --noEmit>

## Routing

- **Route Prefix**: <e.g., /workspace, /app, /dashboard>

## Testing

- **Playwright Session Name**: <e.g., my-app>

## Remote Testing

- **Remote Dev URL**: <e.g., https://dev.agents.dodocs.ai>
- **Tenant Registration URL**: <e.g., https://dev.agents.dodocs.ai/register>
- **Tenant Admin URL**: <e.g., https://dev.agents.dodocs.ai/admin/tenants>

## Test Environment (Docker Isolation)

- **Docker Compose File**: <e.g., docker-compose.yml — or leave blank to skip Docker isolation>
- **Frontend Service Name**: <service name in docker-compose that serves the frontend, e.g., web, frontend>
- **Frontend Internal Port**: <internal container port for frontend, e.g., 3000, 80>
- **Backend Service Name**: <service name in docker-compose for the API, e.g., api, app, backend>
- **Backend Internal Port**: <internal container port for backend, e.g., 8000, 8080>
- **Playwright Service**: <optional: service name in docker-compose for test runner, e.g., playwright — leave blank to run Playwright on host>
