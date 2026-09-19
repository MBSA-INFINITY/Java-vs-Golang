FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/server .

FROM alpine:3.19
RUN adduser -D -u 10001 appuser
COPY --from=build /out/server /server
USER appuser
EXPOSE 8080
ENTRYPOINT ["/server"]
