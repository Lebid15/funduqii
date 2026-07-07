# Funduqii — Media & Object Storage Strategy

> **Status:** strategy established in **Phase 1.5** (expanded). Documentation
> only — no upload features or storage integrations are built yet.

---

## 1. Core rule

- **Images and documents are NEVER stored in the database.** The database holds
  only **references** (path/URL/object key + metadata). This keeps the DB small,
  fast to back up, and cheap to replicate.

## 2. Storage evolution

- **Stage 1 (start):** store media on the server under `media/` (Django
  `MEDIA_ROOT`), served by Nginx. Fine for low volume.
- **Later:** move to **S3-compatible object storage** (e.g. Hetzner Object
  Storage) as volume grows, so app servers stay stateless and horizontally
  scalable.

## 3. Organization & isolation

- Files are namespaced **per tenant/hotel**, e.g. `hotels/<hotel_id>/…`.
- **A hotel can never access another hotel's files.** Access is authorized by
  the backend (tenant scope), not by guessing URLs.
- Private documents (IDs, guest documents) are **not public**; serve them via
  **signed, expiring URLs** issued only to authorized users.

## 4. Handling & optimization

- **Size limits** and allowed content types enforced on upload.
- **Image compression / optimization** and generation of sized variants
  (thumbnails) for lists/cards; originals kept for documents.
- **Lazy-load** images in the UI; never block a request on large media.
- **Clean up unused files** (orphans) via a background job when the owning
  record is deleted/replaced.

## 5. Public vs private

- **Public** (hotel gallery, cover images for the public site): may be cached
  and served via a **CDN** later.
- **Private** (guest documents, internal attachments): signed URLs, short TTL,
  never cached publicly.

## 6. CDN (later)

- Put a CDN in front of public images and the public website for latency and to
  offload the origin. Private/signed content bypasses public caching.

## 7. Out of scope for Phase 1.5

No models, upload endpoints, storage backends, or signed-URL logic are created
now. This document governs how media is handled when those features arrive.
