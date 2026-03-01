# How schedule viewing works (for AI / training)

This describes how **schedule viewing** is implemented across buyer, broker, and landlord so the chatbot can answer "how to book a viewing" / "how to schedule a viewing" accurately.

---

## Buyer flow

1. **Find a property** – Search or open a listing (e.g. `new_property_details.html`, `search_results.html`).
2. **Contact broker/landlord** – Click **Contact** / **Message** on the listing. User must be logged in and KYC verified.
3. **Open Messages** – `docs/buyer/messages.html`: conversation with the broker/landlord for that property.
4. **Click "Schedule Viewing"** – In the conversation toolbar there is a button **Schedule Viewing** (`scheduleViewingBtn`). It builds:
   - `schedule_viewing.html?buyerId=<buyer>&brokerId=<broker>&propertyId=<id>&brokerName=...&propertyName=...`
   - and opens it in a popup (`window.open(..., 'width=800,height=700')`).
5. **Schedule Property Viewing page** – `docs/buyer/schedule_viewing.html`:
   - **Preferred Date**: Flatpickr, within 30 days, Sundays disabled.
   - **Preferred Time**: slots 9 AM–5 PM (hourly).
   - **Notes** (optional).
   - **Request Viewing** → writes to Firestore `schedules` with status `pending`.
6. **Updates** – Broker/landlord can **Confirm**, **Decline**, or **Suggest alternative**. Buyer sees updates in Messages and can accept alternative or cancel from the same schedule page if reopened.

---

## Broker flow

- **Inquiries** – `docs/broker/inquiries.html` (and `agent_inquiries.html`): list of conversations. From a conversation with a buyer about a property, broker can open the **schedule viewing** page with:
  - `../buyer/schedule_viewing.html?brokerId=<broker>&buyerId=<buyer>&propertyId=<id>&buyerName=...&propertyName=...`
- **Schedule management** – `docs/broker/schedule_management.html` and `agent_schedule_management.html`: list/calendar of viewing requests. For **reschedule**, they open:
  - `../buyer/schedule_viewing.html?brokerId=...&buyerId=...&propertyId=...&reschedule=true&scheduleId=<id>`
- On the schedule page, when the current user is the broker (`brokerId === user.uid`), the UI shows **Confirm**, **Decline**, **Suggest alternative**. Schedules are stored in Firestore `schedules`; notifications are sent via the conversation in `messages`.

---

## Landlord flow

- **Inquiries** – `docs/landlord/inquiries.html`: from a conversation with a buyer, landlord opens schedule viewing with:
  - `schedule_viewing.html?buyerId=<buyer>&propertyId=<id>&buyerName=...&propertyName=...`
  - (No `brokerId`; landlord is the owner.)
- Same **Schedule Property Viewing** page (`docs/buyer/schedule_viewing.html`) is used; landlord can confirm/decline/suggest alternative. Reschedule from landlord’s schedule management also opens the buyer `schedule_viewing.html` with the right query params.

---

## How broker and landlord get the viewing part

- **Broker**: From **Inquiries** (`inquiries.html` or `agent_inquiries.html`), open a conversation with a buyer about a property, then click the button that opens the schedule viewing page. URL: `../buyer/schedule_viewing.html?brokerId=<broker>&buyerId=<buyer>&propertyId=<id>&buyerName=...&propertyName=...`. From **Schedule management** (`schedule_management.html`), brokers see all viewing requests; to **reschedule**, they open the same page with `reschedule=true&scheduleId=<id>`.
- **Landlord**: From **Inquiries** (`landlord/inquiries.html`), open a conversation with a buyer, then open the schedule viewing page (no `brokerId`). URL: `schedule_viewing.html?buyerId=<buyer>&propertyId=<id>&buyerName=...&propertyName=...`. Landlords use the same **Schedule Property Viewing** page (`docs/buyer/schedule_viewing.html`) to Confirm, Decline, or Suggest alternative. Reschedule from landlord’s schedule management also opens this page with the right params.
- **Shared page**: All roles use **one page** – `docs/buyer/schedule_viewing.html`. The page shows a date/time form for the buyer; when the current user is the broker or landlord, it shows actions: Confirm, Decline, Suggest alternative. Data is stored in Firestore `schedules`; status flows: `pending` → `confirmed` / `declined` / `alternative` (then buyer can accept alternative or cancel).

## Data and AI

- **Firestore**: `schedules` collection; fields include `buyerId`, `brokerId` (optional for landlord), `propertyId`, `proposedDate`, `proposedTime`, `status` (`pending` | `confirmed` | `declined` | `alternative` | `cancelled`), `conversationId`, etc.
- **Training / chatbot**: The intent **schedule_viewing** is trained so that queries like "how to book a viewing", "how to schedule a viewing", "how can I schedule a viewing" are answered with the steps above. Response text is generated in the backend (`generate_schedule_viewing_response`) and also defined in training data (`schedule_viewing` in `backend/data/member1/training_data.json` and `training/data/member1/training_data.json`) for template/fallback.

---

## Files reference

| Role    | File(s) |
|---------|---------|
| Buyer   | `docs/buyer/schedule_viewing.html`, `docs/buyer/messages.html` (Schedule Viewing button) |
| Broker  | `docs/broker/inquiries.html`, `docs/broker/agent_inquiries.html`, `docs/broker/schedule_management.html`, `docs/broker/agent_schedule_management.html` |
| Landlord| `docs/landlord/inquiries.html`, `docs/landlord/schedule_management.html` |

All roles use the same **Schedule Property Viewing** page: `docs/buyer/schedule_viewing.html`.
