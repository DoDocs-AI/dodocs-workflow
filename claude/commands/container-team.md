Launch the full scrum-team workflow inside an isolated Docker container, freeing the main Claude Code session for other work. The container runs the 13-agent team non-interactively while the main session monitors logs and PROGRESS.md.

## Arguments

`$ARGUMENTS` may be:
- `<feature-name>` — launch a new container team for this feature
- `<feature-name> --detach` — launch and exit immediately (no monitoring loop)
- `<feature-name> --k8s` — use Kubernetes Job instead of Docker
- `--attach <container-id>` — re-enter the monitoring loop for a running container
- `--status` — show all running container-team containers

## Phase 1 — Validate

Run these checks before doing anything else:

1. **Docker available?**
   ```bash
   docker info >/dev/null 2>&1
   ```
   If Docker is not running, check `--k8s` flag; if neither is available, stop with:
   "container-team requires Docker or Kubernetes. Please start Docker Desktop or pass --k8s with a configured cluster."

2. **API key set?**
   ```bash
   echo "${ANTHROPIC_API_KEY:-}"
   ```
   If empty, stop with: "ANTHROPIC_API_KEY is not set in this shell. Export it before running /container-team."

3. **Project config exists?**
   Check for `.claude/scrum-team-config.md` in the current working directory.
   If missing, stop with: "No scrum-team config found. Copy ~/.claude/scrum-team-config.template.md to .claude/scrum-team-config.md and fill in your project values."

4. **Docker files exist?**
   Check for `~/.claude/docker/agent-env.Dockerfile`.
   If missing, stop with: "Docker files not found. Re-run the dodocs-workflow installer to get the latest version."

## Phase 2 — Build Image

Build (or verify) the agent environment Docker image:

```bash
docker build \
  -f "$HOME/.claude/docker/agent-env.Dockerfile" \
  -t dodocs-agent-env:latest \
  "$HOME/.claude/docker/"
```

If the image already exists and `--no-build` is not passed, still build (Docker layer cache makes this fast). Show a brief progress message.

## Phase 3 — Launch Container (Docker mode)

Generate a unique container name and launch the container in detached mode:

```bash
FEATURE_SLUG=$(echo "$FEATURE_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
TIMESTAMP=$(date +%s)
CONTAINER_NAME="ct-${FEATURE_SLUG}-${TIMESTAMP}"

CONTAINER_ID=$(docker run -d \
  --name "$CONTAINER_NAME" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e FEATURE_NAME="$FEATURE_NAME" \
  -e CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \
  -v "$(pwd):/workspace" \
  -v "$HOME/.claude:/root/.claude-host:ro" \
  dodocs-agent-env:latest)
```

Create the tracking directory and save the container ID:
```bash
mkdir -p ".container-team/$FEATURE_NAME"
echo "$CONTAINER_ID" > ".container-team/$FEATURE_NAME/container.id"
echo "$CONTAINER_NAME" > ".container-team/$FEATURE_NAME/container.name"
date -u +"%Y-%m-%dT%H:%M:%SZ" > ".container-team/$FEATURE_NAME/started.at"
```

Print launch summary:
```
Container Team launched!
  Feature:    <feature-name>
  Container:  <container-name>
  ID:         <short-id>

Monitor:  docker logs -f <container-name>
Reattach: /container-team --attach <container-name>
Stop:     docker stop <container-name>
```

If `--detach` flag was passed, stop here and print the above summary. Do NOT enter the monitoring loop.

## Phase 3 — Launch Job (K8s mode)

If `--k8s` flag is passed or `kubectl cluster-info` succeeds and Docker is not available:

Generate the Job manifest and write it to `/tmp/ct-<feature-slug>-<timestamp>-job.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: ct-<feature-slug>-<timestamp>
  labels:
    container-team: "true"
    feature: <feature-slug>
spec:
  backoffLimit: 1
  template:
    spec:
      containers:
      - name: scrum-team
        image: ghcr.io/dodocs-ai/agent-env:latest
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: anthropic-api-key
              key: key
        - name: FEATURE_NAME
          value: "<feature-name>"
        - name: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
          value: "1"
        volumeMounts:
        - name: workspace
          mountPath: /workspace
        - name: claude-config
          mountPath: /root/.claude-host
          readOnly: true
      volumes:
      - name: workspace
        persistentVolumeClaim:
          claimName: workspace-pvc
      - name: claude-config
        secret:
          secretName: claude-config
      restartPolicy: Never
```

Apply it:
```bash
kubectl apply -f /tmp/ct-<feature-slug>-<timestamp>-job.yaml
```

Monitor with:
```bash
kubectl logs -f job/ct-<feature-slug>-<timestamp>
```

## Phase 4 — Monitoring Loop

**Skip this phase if `--detach` was passed.**

Enter a live monitoring loop. Refresh every 15 seconds:

1. Check container status:
   ```bash
   docker inspect --format='{{.State.Status}}' <container-name>
   docker inspect --format='{{.State.StartedAt}}' <container-name>
   ```

2. Read PROGRESS.md if it exists:
   ```
   docs/features/<feature-name>/PROGRESS.md
   ```

3. Get recent logs:
   ```bash
   docker logs --tail 20 <container-name>
   ```

4. Display the dashboard:
   ```
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Container Team: <feature-name>
   Container: <container-name>  |  Status: running  |  Uptime: 14m
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   PROGRESS (docs/features/<feature>/PROGRESS.md)
     Phase 1: Requirements + UX Research   ✅ Done
     Phase 2: UX Design + Architecture     🔄 In Progress
     Phase 3: Task Breakdown + Git         ⏳ Pending
     Phase 4: Build + Test                 ⏳ Pending
     Phase 5: Integration Verification     ⏳ Pending
     Phase 6: Ship                         ⏳ Pending

   RECENT LOGS (last 20 lines):
     [product-owner] Feature Brief written to docs/features/...
     [ux-designer]   Researching existing UI patterns...
     [architect]     Reading Feature Brief, designing architecture...

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Refreshing in 15s...  [Use Ctrl+C or tell me "q" to stop monitoring]
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

5. Parse the PROGRESS.md phase status table and render:
   - `✅ Done` for phases marked `Complete` or `Done`
   - `🔄 In Progress` for the current phase
   - `⏳ Pending` for future phases

6. If the user says "q", "quit", or "stop monitoring" — exit the monitoring loop but leave the container running. Print:
   ```
   Monitoring stopped. Container is still running.
   Resume monitoring: /container-team --attach <container-name>
   Logs:              docker logs -f <container-name>
   ```

7. If the user says "l" or "full logs" — stream `docker logs -f <container-name>` until interrupted.

## Phase 5 — Completion

When the container exits (status becomes `exited`):

1. Get exit code:
   ```bash
   docker inspect --format='{{.State.ExitCode}}' <container-name>
   ```

2. If exit code is 0:
   ```
   ✅ Container Team completed successfully!
   Feature: <feature-name>
   Container: <container-name>

   Check docs/features/<feature-name>/PROGRESS.md for the full summary.
   ```
   Also check if a PR was created (look for PR URL in recent logs) and show it.

3. If exit code is non-zero:
   ```
   ❌ Container Team failed (exit code: <N>)
   Feature: <feature-name>
   Container: <container-name>

   View full logs: docker logs <container-name>
   ```

4. Ask the user: "Remove the container? (y/n)"
   - If yes: `docker rm <container-name>`
   - If no: leave it for manual inspection

## Attach Mode

If `$ARGUMENTS` starts with `--attach`:

1. Parse the container name/ID from arguments
2. Verify the container exists: `docker inspect <container-name>`
3. If not found, show error: "Container <name> not found. Use `docker ps -a | grep ct-` to list container-team containers."
4. Read `.container-team/*/container.name` to find the matching feature name
5. Enter Phase 4 monitoring loop as normal

## Status Mode

If `$ARGUMENTS` is `--status` (no feature name):

Show all running container-team containers:

```bash
docker ps --filter "name=ct-" --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}"
```

Also list any tracking files in `.container-team/`:
```
Active Container Teams:
  ct-billing-dashboard-1708001234   running   14 minutes
  ct-dark-mode-1707998765           running   2 hours

Reattach: /container-team --attach <container-name>
```

## Error Handling

- If `docker build` fails: show the build output and stop. The user needs to fix the Dockerfile or check Docker daemon.
- If `docker run` fails: show the error. Common causes: port conflicts (unlikely for this use case), image not found, volume mount issues.
- If the container starts but immediately exits: check logs with `docker logs <container-name>` and show the last 50 lines.
- If PROGRESS.md is not yet created (Phase 1 still starting): show a message like "Waiting for scrum team to initialize..." instead of a phase table.

## Notes

- The container mounts the current project directory as `/workspace` — agents read and write files there directly, so PROGRESS.md and all feature docs appear in the host project in real time.
- The host `~/.claude` is mounted read-only as `/root/.claude-host` — the entrypoint copies it at startup so agents have access to all installed agent definitions and commands.
- Multiple features can run simultaneously in separate containers.
- Container names follow the pattern `ct-<feature-slug>-<timestamp>` for easy filtering.
- The `.container-team/` directory in the project root tracks active container metadata. Add it to `.gitignore` if desired.
