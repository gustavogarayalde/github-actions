FROM amazoncorretto:21-alpine
ARG JAR_FILE=target/api.jar
COPY ${JAR_FILE} api.jar
ENTRYPOINT ["java","-jar","/api.jar"]
