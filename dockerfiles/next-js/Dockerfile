# Dependencies stage
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Accept GitHub token as build argument
ARG NPM_TOKEN

# Copy dependency files and .npmrc
COPY package.json package-lock.json* .npmrc* ./

# Configure npm authentication for GitHub Packages
RUN if [ -n "$NPM_TOKEN" ]; then \
    echo "//npm.pkg.github.com/:_authToken=${NPM_TOKEN}" >> .npmrc; \
    fi

# Install dependencies using ci for reproducible builds
RUN npm ci --legacy-peer-deps

# Clean up authentication from this layer
RUN rm -f .npmrc

# Builder stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build Next.js with standalone output for minimal runtime
RUN npm run build

# Production runtime stage
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV production
RUN apk add --no-cache jq

# Copy necessary files for runtime
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY ./start.sh ./start.sh
COPY ./next.config.js ./next.config.js

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
RUN chown -R nextjs:nodejs /app

USER nextjs
EXPOSE 3000
ENV PORT 3000

CMD ["./start.sh"]
