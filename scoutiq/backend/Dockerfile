FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package.json ./

# Install dependencies
RUN npm install --production

# Copy source
COPY server.js ./

# Data volume mount point
RUN mkdir -p /app/data

EXPOSE 3001

CMD ["node", "server.js"]
