FROM node:22-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    gnupg \
    lsb-release \
    postgresql-client \
    jq \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl" \
    -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Install AWS CLI v2 (required for EKS authentication)
RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/* && \
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip && \
    cd /tmp && unzip awscliv2.zip && ./aws/install && \
    rm -rf /tmp/aws /tmp/awscliv2.zip

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Set environment
ENV CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
ENV NODE_ENV=production

# Create non-root user (Claude CLI refuses --dangerously-skip-permissions as root)
RUN groupadd -r botuser && useradd -r -g botuser -m -d /home/botuser botuser

WORKDIR /app

# Install Python dependencies
COPY gateway/requirements.txt /app/gateway/requirements.txt
RUN python3 -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir -r /app/gateway/requirements.txt

# Copy application code
COPY gateway/ /app/gateway/
COPY config/ /app/config/
COPY claude/ /app/claude/

# Copy entrypoint
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set ownership for app directory
RUN chown -R botuser:botuser /app

EXPOSE 8888

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
