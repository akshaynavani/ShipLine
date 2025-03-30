"""Tiny Flask service used to exercise the ShipLine pipeline end to end."""

from __future__ import annotations

import os
import socket

from flask import Flask, jsonify


def create_app() -> Flask:
    app = Flask(__name__)
    version = os.environ.get("APP_VERSION", "dev")

    @app.get("/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/readyz")
    def readyz() -> tuple[dict[str, str], int]:
        return {"status": "ready"}, 200

    @app.get("/")
    def index():  # type: ignore[no-untyped-def]
        return jsonify(
            service="hello-service",
            version=version,
            host=socket.gethostname(),
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
