# Dependencies stage
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy dependency files only (for better caching)
COPY package.json package-lock.json* ./
# Install dependencies using ci for reproducible builds
RUN npm ci --legacy-peer-deps

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
