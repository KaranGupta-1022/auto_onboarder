# Repository: ghostkube-fixtures/storefront


## File Path: services/auth/login.py
"""User login and password authentication."""
import bcrypt
import jwt

def verify_password(plain_password, password_hash):
    return bcrypt.checkpw(plain_password.encode(), password_hash.encode())

def issue_access_token(user_id, secret_key):
    payload = {"sub": user_id, "type": "access"}
    return jwt.encode(payload, secret_key, algorithm="HS256")

def login(username, password, user_store, secret_key):
    user = user_store.get_by_username(username)
    if user is None or not verify_password(password, user.password_hash):
        raise ValueError("invalid credentials")
    return issue_access_token(user.id, secret_key)


## File Path: services/auth/middleware.py
"""Request authentication middleware.

Verifies the JWT bearer token on every incoming request and attaches the
decoded user identity to the request context before the handler runs.
"""
import jwt

def authenticate_request(request, secret_key):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise PermissionError("missing bearer token")
    token = header[len("Bearer "):]
    claims = jwt.decode(token, secret_key, algorithms=["HS256"])
    request.state.user_id = claims["sub"]
    return claims


## File Path: services/auth/password_reset.py
"""Password reset flow: emails a one-time reset token and later verifies it."""
import secrets

from services.notifications.email import send_email

_reset_tokens = {}

def request_password_reset(user_email, api_key):
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = user_email
    send_email(user_email, "Reset your password", f"Your reset code is {token}", api_key)
    return token

def confirm_password_reset(token, new_password_hash, user_store):
    email = _reset_tokens.pop(token, None)
    if email is None:
        raise ValueError("invalid or expired reset token")
    user_store.update_password_hash(email, new_password_hash)


## File Path: services/payments/charge.py
"""Stripe charge creation for one-time credit card payments."""
import stripe

def create_charge(amount_cents, currency, card_token, idempotency_key):
    return stripe.Charge.create(
        amount=amount_cents,
        currency=currency,
        source=card_token,
        idempotency_key=idempotency_key,
    )

def capture_pending_charge(charge_id):
    return stripe.Charge.capture(charge_id)


## File Path: services/payments/refund.py
"""Refund processing - reverses a previously captured Stripe charge."""
import stripe

def refund_charge(charge_id, amount_cents=None, reason="requested_by_customer"):
    kwargs = {"charge": charge_id, "reason": reason}
    if amount_cents is not None:
        kwargs["amount"] = amount_cents
    return stripe.Refund.create(**kwargs)


## File Path: services/notifications/email.py
"""Transactional email delivery via SendGrid."""
import sendgrid

def send_email(to_address, subject, html_body, api_key):
    client = sendgrid.SendGridAPIClient(api_key)
    message = {
        "personalizations": [{"to": [{"email": to_address}]}],
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    return client.send(message)


## File Path: services/notifications/sms.py
"""SMS notification delivery via Twilio."""
from twilio.rest import Client

def send_sms(to_number, body, account_sid, auth_token, from_number):
    client = Client(account_sid, auth_token)
    return client.messages.create(to=to_number, from_=from_number, body=body)


## File Path: services/database/connection.py
"""Postgres connection pool setup shared by every service."""
import psycopg2.pool

_pool = None

def get_pool(dsn, minconn=1, maxconn=10):
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(minconn, maxconn, dsn)
    return _pool


## File Path: services/database/migrations.py
"""Alembic migration runner invoked at deploy time."""
from alembic.config import Config
from alembic import command

def run_migrations(alembic_ini_path):
    cfg = Config(alembic_ini_path)
    command.upgrade(cfg, "head")


## File Path: services/orders/create_order.py
"""Creates a new order record after validating inventory availability."""
from services.inventory.stock import reserve_stock

def create_order(order_store, customer_id, line_items):
    for item in line_items:
        reserve_stock(item["sku"], item["quantity"])
    return order_store.insert(customer_id=customer_id, line_items=line_items, status="pending")


## File Path: services/orders/cancel_order.py
"""Cancels an existing order and issues a refund through the payments module."""
from services.payments.refund import refund_charge

def cancel_order(order_store, order_id):
    order = order_store.get(order_id)
    if order.charge_id:
        refund_charge(order.charge_id)
    order_store.update_status(order_id, "cancelled")
    return order


## File Path: services/inventory/stock.py
"""Tracks warehouse stock levels and decrements them as orders are placed."""
class InsufficientStockError(Exception):
    pass

def reserve_stock(sku, quantity, stock_table):
    available = stock_table.get(sku, 0)
    if available < quantity:
        raise InsufficientStockError(f"not enough stock for {sku}")
    stock_table[sku] = available - quantity


## File Path: services/search/indexer.py
"""Builds the full-text search index for the product catalog."""
def build_index(products):
    index = {}
    for product in products:
        for token in product["title"].lower().split():
            index.setdefault(token, set()).add(product["id"])
    return index


## File Path: services/logging/logger.py
"""Structured JSON logger setup wrapping the stdlib logging module."""
import json
import logging

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"level": record.levelname, "message": record.getMessage()})

def configure_logger(name):
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


## File Path: frontend/components/Cart.jsx
// Shopping cart React component - lists line items and the running total.
import React from "react";

export default function Cart({ items, onRemove }) {
  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  return (
    <div className="cart">
      {items.map((item) => (
        <div key={item.sku}>
          {item.title} x{item.quantity}
          <button onClick={() => onRemove(item.sku)}>Remove</button>
        </div>
      ))}
      <div className="cart-total">Total: {total}</div>
    </div>
  );
}


## File Path: frontend/components/Checkout.jsx
// Checkout form React component, collects card details via Stripe Elements.
import React from "react";
import { CardElement, useStripe, useElements } from "@stripe/react-stripe-js";

export default function Checkout({ onSubmit }) {
  const stripe = useStripe();
  const elements = useElements();

  const handleSubmit = async (event) => {
    event.preventDefault();
    const card = elements.getElement(CardElement);
    const result = await stripe.createToken(card);
    onSubmit(result.token);
  };

  return (
    <form onSubmit={handleSubmit}>
      <CardElement />
      <button type="submit">Pay</button>
    </form>
  );
}


## File Path: frontend/utils/api.js
// Fetch wrapper used by every frontend component to call the backend REST API.
export async function apiRequest(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json();
}


## File Path: infra/docker-compose.yml
# Local dev docker compose config wiring up every backend service and Postgres.
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: devpassword
  orders:
    build: ./services/orders
    depends_on:
      - postgres
  payments:
    build: ./services/payments
    depends_on:
      - postgres


## File Path: infra/k8s/deployment.yaml
# Kubernetes deployment manifest for the orders service.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders-service:latest
          ports:
            - containerPort: 8080


## File Path: scripts/seed_db.py
"""Seeds the local database with fake customers, products, and orders."""
def seed(order_store, product_store, customer_store):
    customer_store.insert(name="Test Customer", email="test@example.com")
    product_store.insert(sku="SKU-1", title="Widget", price=999)
    order_store.insert(customer_id=1, line_items=[{"sku": "SKU-1", "quantity": 2}])


## File Path: docs/README.md
# Fixture Storefront

A small fake e-commerce backend used only as a hermetic retrieval fixture for
GhostKube's test suite. It has auth, payments, notifications, orders,
inventory, search, and a minimal React frontend, wired together with docker
compose and a Kubernetes deployment manifest for the orders service.
ok