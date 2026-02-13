# Production runtime stage
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV production
RUN apk add --no-cache jq

# Copy build artifacts from GitHub Actions build
COPY ./public ./public
COPY ./.next/standalone ./
COPY ./.next/static ./.next/static
COPY ./start.sh ./start.sh
COPY ./next.config.js ./next.config.js

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
RUN chown -R nextjs:nodejs /app

USER nextjs
EXPOSE 3000
ENV PORT 3000

CMD ["./start.sh"]
