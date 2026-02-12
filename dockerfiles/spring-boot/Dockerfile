FROM amazoncorretto:21-alpine
ARG JAR_FILE=target/api.jar
ARG OTEL_AGENT_VERSION=2.24.0
RUN apk add --no-cache curl \
    && curl -L -o /opentelemetry-javaagent.jar \
    "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${OTEL_AGENT_VERSION}/opentelemetry-javaagent.jar"
COPY ${JAR_FILE} api.jar
ENTRYPOINT ["java","-javaagent:/opentelemetry-javaagent.jar","-jar","/api.jar"]
