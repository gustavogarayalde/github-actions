FROM node:16-alpine
COPY ./package.json .
COPY ./.next ./.next
COPY ./next.config.js .
COPY ./node_modules ./node_modules
COPY ./public ./public
EXPOSE 3000
CMD ["node_modules/.bin/next", "start"]
