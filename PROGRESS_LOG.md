# Funduqii / فندقي — Progress Log (سجل تنفيذ المراحل)

> **الغرض:** مرجع موثّق يبيّن ماذا نُفّذ في كل مرحلة من مراحل المشروع، ونتيجة كل مرحلة، والتواريخ، وما تبقّى.
> **قاعدة التحديث:** بعد إغلاق أي مرحلة، أضِف قسمها هنا (أو حدّثه) قبل بدء المرحلة التالية.
> **المرجعان الأساسيان:** [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md) (خطة المشروع) و [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) (قواعد التطوير).
> **حالة الاعتماد:** لا تُعلَّم مرحلة «مكتملة ✅» إلا بعد اعتماد المالك. المراحل المنفَّذة والمُختبَرة بانتظار المراجعة تُعلَّم «بانتظار الاعتماد 🔎».
> **آخر تحديث:** 2026-07-09

---

## كيفية استخدام هذا الملف

- كل مرحلة لها قسم بعنوان `## Phase N — <الاسم>`.
- كل قسم يتبع نفس القالب: الحالة، التاريخ، الهدف، ما نُفّذ، الملفات، الفحوصات/النتائج، ملاحظات/قرارات، ما لم يُنفَّذ.
- الحالات المسموحة: `مكتملة ✅` · `قيد التنفيذ 🚧` · `لم تبدأ ⏳` · `محظورة/موقوفة ⛔`.
- لا يُعتبر أي شيء «منجزًا» إلا إذا كان مُختبَرًا (انظر قواعد التطوير).

### قالب المرحلة (انسخه عند بدء مرحلة جديدة)

```
## Phase N — <الاسم>
- الحالة: 🚧 قيد التنفيذ
- التاريخ: بدأت YYYY-MM-DD · اكتملت —
- الهدف: <جملة واحدة>

### ما نُفّذ
- ...

### الملفات المضافة/المعدّلة
- ...

### الفحوصات والنتائج
- ...

### ملاحظات وقرارات
- ...

### ما لم يُنفَّذ (مؤجّل)
- ...
```

---

## نظرة عامة على تقدّم المراحل

| Phase | العنوان | الحالة | التاريخ |
|------|---------|--------|---------|
| 0 | Project Blueprint | مكتملة ✅ | 2026-07-07 |
| 1 | Technical Foundation | مكتملة ✅ | 2026-07-07 |
| 1.5 | Production-Ready Scalability, Performance, Realtime & Hetzner Readiness | مكتملة ✅ | 2026-07-07 |
| 1.6 | Maps, Messaging & External Integrations Foundation | مكتملة ✅ | 2026-07-07 |
| 1.7 | Governance, Compliance, QA & Release Foundation | مكتملة ✅ | 2026-07-07 |
| 1.8 | Legacy Reference Insights & Product Enhancements Alignment | مكتملة ✅ | 2026-07-07 |
| 2 | Authentication + Users + Permissions | مكتملة ✅ | 2026-07-07 |
| 3 | Platform Owner Panel basics | مكتملة ✅ | 2026-07-07 |
| 3.1 | Premium UI Design System & Visual Polish | مكتملة ✅ | 2026-07-07 |
| 4 | Hotels + Hotel Settings | مكتملة ✅ | 2026-07-07 |
| 5 | Floors + Room Types + Rooms | مكتملة ✅ | 2026-07-07 |
| 6 | Reservations + Availability Engine | مكتملة ✅ | 2026-07-07 |
| 7 | Guests + Check-in + Check-out | مكتملة ✅ | 2026-07-07 |
| 8 | Payments + Expenses + Folio + Invoices | مكتملة ✅ | 2026-07-07 |
| 9 | Restaurant / Café / Room Service Orders | مكتملة ✅ | 2026-07-08 |
| 10 | Housekeeping + Maintenance + Lost & Found | مكتملة ✅ | 2026-07-08 |
| 11 | Staff + Permissions Management UI | مكتملة ✅ | 2026-07-08 |
| 12 | Shifts + Handover + Daily Close | مكتملة ✅ | 2026-07-08 |
| 13 | Reports + Analytics | مكتملة ✅ | 2026-07-08 |
| 14 | Notifications + Activity Center | مكتملة ✅ | 2026-07-09 |
| 15 | Public Website + Public Booking | مكتملة ✅ | 2026-07-09 |
| 16 | Platform Owner Panel Completion | مكتملة ✅ | 2026-07-09 |
| 17 | Mobile / PWA / Offline / Performance | مكتملة ✅ | 2026-07-09 |
| 18 | Hardening + QA + Release | لم تبدأ ⏳ | — |

### ملاحظات شاملة (Cross-cutting mandates)
- **إلزام الواجهة المركزية (UI/UX/Responsive/Translation) — نافذ من Phase 3 فصاعدًا** (2026-07-07): ممنوع بناء أي صفحة/مكوّن بشكل عشوائي؛ يجب استخدام design tokens + مكوّنات مركزية + الترجمة المركزية (ar/en/tr مع RTL/LTR تلقائي) + layout مركزي + حالات موحّدة (loading/empty/error/…) + responsive حقيقي + accessibility + API client المركزي، مع احترام الصلاحيات وfeature flags وبقاء الباكند مصدر الحقيقة. المرجع: `docs/FRONTEND_DESIGN_SYSTEM_GUIDELINES.md` + `DEVELOPMENT_RULES.md` (قسم 16) + ملحق في `PROJECT_BLUEPRINT.md`. (توثيق قواعد؛ ليس مرحلة وليس بناء واجهات.)

---

## Phase 0 — Project Blueprint
- الحالة: مكتملة ✅
- التاريخ: بدأت 2026-07-07 · اكتملت 2026-07-07
- الهدف: إنشاء مخطط رسمي كامل للمشروع قبل كتابة أي كود.

### ما نُفّذ
- كتابة مخطط المشروع الكامل في `PROJECT_BLUEPRINT.md` بـ 24 قسمًا يغطّي: تعريف المشروع، المستخدمين والأدوار، اللوحات الثلاث، دورة التشغيل الكاملة (46 خطوة)، الاشتراكات، الحجز، الغرف والتوفر، النزلاء، المال والفوليو، المطعم/الكافتيريا، التنظيف/الصيانة، الورديات والإغلاق اليومي، الصلاحيات، الترجمة، التصميم المركزي، الموقع العام، البنية التقنية، قواعد API، قاعدة البيانات المفاهيمية، الاختبارات، مراحل التنفيذ، والأخطاء الممنوع تكرارها.

### الملفات المضافة/المعدّلة
- `PROJECT_BLUEPRINT.md` (المخطط الرسمي المعتمد).

### الفحوصات والنتائج
- مراجعة تغطية الأقسام مقابل المتطلبات: مطابقة ✅.
- لا كود، لا Models، لا صفحات — تخطيط فقط ✅.

### ملاحظات وقرارات
- **قرار العزل (Multi-Tenancy):** قاعدة بيانات مشتركة مع عزل على مستوى الصف (`hotel_id` scoping) — قابل لإعادة النظر قبل Phase 2 إن لزم عزل أقوى.
- نقاط قابلة للتهيئة تُحسم لاحقًا: سياسة المغادرة برصيد غير مسدد (Phase 8)، وسلوك الحجز العام الافتراضي pending/confirmed (Phase 6/12).

### ما لم يُنفَّذ (مؤجّل)
- أي تنفيذ فعلي (يبدأ من Phase 1).

---

## Phase 1 — Technical Foundation (تأسيس البنية التقنية)
- الحالة: مكتملة ✅
- التاريخ: بدأت 2026-07-07 · اكتملت 2026-07-07
- الهدف: تأسيس أساس تقني نظيف ومنظّم (Monorepo: backend + frontend) دون أي ميزة تشغيلية.

### ما نُفّذ

**Backend (Django + DRF):**
- مشروع Django 5.1 + Django REST Framework بإعدادات مقسّمة: `base` / `development` / `production`.
- إدارة الإعدادات من env عبر `django-environ` (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`, `LANGUAGE_CODE`, `TIME_ZONE`).
- `django-cors-headers`، إعداد static/media أولي، وإعدادات production منفصلة (أمان HSTS/SSL + Logging).
- **PostgreSQL هي القاعدة المعتمدة** (عبر `DATABASE_URL` + `docker-compose.yml`)، مع fallback إلى SQLite في التطوير فقط ليعمل التشغيل الأول والاختبارات دون Postgres.
- تطبيق `apps/core` للبنية التحتية، وendpoint وحيد: `GET /api/health/` → `{"status":"ok","service":"funduqii-api"}`.
- اختبار للـ health endpoint.

**Frontend (Next.js 16 + TS):**
- تطبيق Next.js 16 + React 19 + TypeScript + ESLint (flat config).
- نظام ترجمة مركزي أولي (ar / en / tr) مع دعم اتجاه RTL/LTR تلقائيًا، ومفاتيح أولية فقط.
- نظام تصميم أولي: `tokens.css` (ألوان، neutral، spacing، radius، خطوط، layout، ظل) + primitives مشتركة (`Container`, `Card`).
- API client موحّد يقرأ `NEXT_PUBLIC_API_BASE_URL` (بدون auth/JWT — مؤجّل لـ Phase 2).
- صفحة بداية مؤقتة مترجمة تعرض «تم تأسيس منصة فندقي بنجاح» فقط (بلا نصوص hardcoded).

**الجذر / البنية التحتية:**
- `README.md`, `DEVELOPMENT_RULES.md`, `.env.example` (جذر + لكل تطبيق), `.gitignore`, `docker-compose.yml` (PostgreSQL للتطوير), `docs/README.md`.

### الملفات المضافة/المعدّلة
- **Backend:** `backend/manage.py`, `backend/config/{__init__,urls,wsgi,asgi}.py`, `backend/config/settings/{__init__,base,development,production}.py`, `backend/apps/__init__.py`, `backend/apps/core/{__init__,apps,views,urls,tests}.py`, `backend/requirements/{base,development,production}.txt`, `backend/.env.example`.
- **Frontend:** `frontend/src/app/{layout,page}.tsx`, `frontend/src/components/{ui/Card,layout/Container}.tsx`, `frontend/src/lib/api/client.ts`, `frontend/src/lib/i18n/{config,dictionaries}.ts`, `frontend/src/lib/i18n/dictionaries/{ar,en,tr}.json`, `frontend/src/lib/{constants,utils}/index.ts`, `frontend/src/styles/{globals,tokens}.css`, `frontend/.env.local.example`. (حُذفت ملفات القالب `app/globals.css`, `app/page.module.css`.)
- **الجذر:** `README.md`, `DEVELOPMENT_RULES.md`, `.env.example`, `.gitignore`, `docker-compose.yml`, `docs/README.md`.

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `python manage.py check` | ✅ لا مشاكل |
| `python manage.py test` | ✅ `Ran 1 test — OK` (`test_health_returns_ok`) |
| فحص حيّ HTTP على `/api/health/` | ✅ `200` + `{"status":"ok","service":"funduqii-api"}` |
| `npm run lint` (eslint) | ✅ exit 0 |
| `tsc --noEmit` | ✅ لا أخطاء أنواع |
| `npm run build` | ✅ `Compiled successfully` (static prerender) |

### ملاحظات وقرارات
- **إصدارات مثبّتة:** Django 5.1.15، DRF 3.15.2، django-environ 0.12، django-cors-headers 4.9، psycopg 3.3 (binary) · Next.js 16.2.10، React 19.2، TypeScript 5.
- **Next.js 16 أحدث وبتغييرات جذرية:** Turbopack افتراضي للبناء، وإزالة `next lint` (السكربت الآن `eslint`). راجعت الوثائق المرفقة، وتجنّبت `next/font/google` لإزالة اعتماد الشبكة أثناء البناء (استخدمت خط النظام عبر tokens).
- **اكتشاف اختبارات Django** يعتمد على مجلد العمل: يجب تشغيل `manage.py test` من داخل `backend/` (المسار الموثّق في README).
- لا أسرار حقيقية في المستودع؛ فقط ملفات `.env.example` بقيم أمثلة.

### ما لم يُنفَّذ (مؤجّل حسب المراحل)
- Authentication، المستخدمون، الصلاحيات، لوحة صاحب المنصة، لوحة الفندق، الموقع العام، وكل Models الأعمال (فنادق/غرف/حجوزات/مال/اشتراكات). لا Dashboard/Login/Public Website. لا seed data.

---

## Phase 2 — Authentication + Users + Permissions + Multi-Tenant Foundation
- الحالة: مكتملة ✅ (معتمدة من المالك)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · تاريخ الاعتماد: 2026-07-07
- الهدف: بناء أساس الأمان — مستخدم مخصّص، JWT، عزل Multi-Tenant بالحد الأدنى، ونظام صلاحيات `section.operation` مفروض من الباكند. بدون أي واجهات أو ميزات تشغيلية.

### ما نُفّذ

**التطبيقات الجديدة (فصل المسؤوليات):**
- `apps/accounts` — المستخدم المخصّص والمصادقة. `apps/tenancy` — الفندق/المستأجر والعضوية وحلّ سياق الفندق. `apps/rbac` — سجل الصلاحيات ومنحها والفرض. `apps/common` — طبقة الأخطاء الموحّدة. (`apps/core` بقي للبنية التحتية/health فقط.)

**المصادقة والمستخدم:**
- Custom User Model (`accounts.User`, جدول `users`): `email` معرّف الدخول الفريد، `full_name`, `phone`, `avatar_url`, `account_type` (platform_owner / hotel_user), `is_active`, `is_staff`, `date_joined` + مدير مخصّص (`create_user` / `create_platform_owner` / `create_superuser`). المستخدم غير النشط يُمنع من الدخول تلقائيًا.
- JWT عبر `djangorestframework-simplejwt` + `token_blacklist`. Endpoints: `token/`, `token/refresh/`, `logout/` (blacklist), `me/`, `context/`.
- أمر آمن `create_platform_owner` (كلمة المرور من arg → env `FUNDUQII_PLATFORM_OWNER_PASSWORD` → prompt؛ لا أسرار في الكود).

**العزل Multi-Tenant (حد أدنى):**
- `tenancy.Hotel` (جدول `hotels`): `name`, `slug`, `status` (setup/active/suspended), timestamps — أساس فقط، بلا إدارة/إعدادات/صور/باقات.
- `tenancy.HotelMembership` (جدول `hotel_users`): user↔hotel، `membership_type` (manager/staff)، `is_active`, `is_primary_manager` + قيود فريدة (عضوية واحدة لكل user/hotel، ومدير رئيسي واحد لكل فندق).
- Tenant Context Resolver عبر ترويسة `X-Hotel-ID`: يتحقق من وجود الفندق وعضوية المستخدم الفعّالة؛ يرفض فندقًا لا يملكه؛ صاحب المنصة ليس موظف فندق بلا عضوية صريحة.

**الصلاحيات (`section.operation`):**
- Registry مركزي (`rbac/registry.py`) — مصدر الحقيقة للأكواد المعتمدة؛ منح كود غير معروف مرفوض (نموذجيًا وخدميًا).
- `rbac.HotelPermissionGrant` (جدول `permissions`) لمنح الصلاحيات لكل عضوية.
- خدمات: `has_hotel_permission`, `get_hotel_permissions`, `grant/revoke`. Manager يملك كل صلاحيات فندقه افتراضيًا؛ staff يملك الممنوح فقط؛ الصلاحية سارية داخل فندق العضوية فقط.
- DRF permission classes قابلة لإعادة الاستخدام: `IsAuthenticatedAndActive`, `IsPlatformOwner`, `HasHotelMembership`, `HasHotelPermission("code")` — الفرض من الباكند لا من إخفاء الأزرار.

**الأخطاء الموحّدة:** مغلّف `{code, message, details?}` عبر exception handler مخصّص (أكواد: `not_authenticated`, `user_inactive`, `hotel_context_required`, `hotel_not_found`, `no_hotel_membership`, `membership_inactive`, `permission_denied`, `unknown_permission`, `no_active_account`, ...).

**الفرونت (بلا UI):** توسيع API client لدعم `Authorization: Bearer` و`X-Hotel-ID` بشكل قابل للتوسع + أنواع DTO للمصادقة. لا صفحات، لا localStorage كمصدر حقيقة.

### الملفات المضافة/المعدّلة (أبرزها)
- جديدة: `apps/common/{__init__,exceptions}.py`؛ `apps/accounts/*` (models, managers, serializers, views, urls, tests, management/commands/create_platform_owner)؛ `apps/tenancy/*` (models, context, tests)؛ `apps/rbac/*` (registry, models, services, permissions, views, urls, tests)؛ migrations `0001_initial` للتطبيقات الثلاثة؛ `frontend/src/lib/api/types.ts`.
- معدّلة: `config/settings/base.py` (AUTH_USER_MODEL، apps، DRF auth/permissions/exception-handler، SIMPLE_JWT، CORS header)؛ `config/urls.py`؛ `requirements/base.txt` (+ simplejwt)؛ `frontend/src/lib/api/client.ts`؛ `README.md`.

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| `manage.py migrate` | ✅ ناجح |
| `manage.py test` (SQLite) | ✅ **39/39 OK** |
| `manage.py test` (PostgreSQL 16 via Docker, منفذ 5433) | ✅ **39/39 OK** |
| Live HTTP (token → me → platform ping، ورفض 401) | ✅ ناجح على PostgreSQL |
| `create_platform_owner` | ✅ ينشئ owner، ويرفض التكرار |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح |

### ملاحظات وقرارات
- **اختُبِر على PostgreSQL فعليًا** عبر حاوية Docker مؤقتة (`postgres:16-alpine`) على المنفذ 5433 (لتفادي تعارض مع PostgreSQL 18 محلي يشغل 5432). العزل والصلاحيات مؤكدة على PostgreSQL.
- إصلاح circular import: استيراد DRF `exception_handler` بشكل مؤجّل داخل الدالة.
- إضافة قيد «مدير رئيسي واحد لكل فندق» (مستمدّ من script1) ضمن أساس العضوية فقط.
- Docker Desktop كان متوقفًا فشُغّل لهذا الاختبار؛ الحاوية المؤقتة أُزيلت بعد الاختبار.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- لا Login/Register/Dashboard UI، لا لوحات، لا موقع عام. لا CRUD للفنادق ولا إعدادات فندق ولا باقات/اشتراكات. لا حجوزات/غرف/نزلاء/مال/مطعم/تنظيف/صيانة/ورديات/إغلاق/تقارير. لا Audit Log كامل. لا seed data. `apps/rbac` و`apps/platform` foundation probes فقط (لا أقسام تشغيلية).

### الاعتماد
- **معتمدة من المالك بتاريخ 2026-07-07** (مقبولة فنيًا). ملاحظات الاعتماد:
  1. التنفيذ مقبول لأنه أنشأ أساس المصادقة والمستخدمين والصلاحيات والعزل فقط.
  2. لا توجد واجهات Login أو Dashboard.
  3. لا توجد ميزات تشغيلية خارج المرحلة.
  4. اختبارات SQLite وPostgreSQL ناجحة.
  5. foundation probes مقبولة مؤقتًا بشرط أن تبقى موثّقة كأدوات Foundation فقط وليست ميزات تشغيلية.
  6. القرار: عدم الانتقال إلى Phase 3 الآن؛ المرحلة التالية هي **Phase 1.5 — Scalability, Performance & Realtime Foundation**.

---

## Phase 1.5 — Production-Ready Scalability, Performance, Realtime & Hetzner Readiness
- الحالة: مكتملة ✅ (معتمدة من المالك)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · تاريخ الاعتماد: 2026-07-07
- الهدف: تأسيس الأداء والتوسّع والتحديث اللحظي **وجاهزية الإنتاج على Hetzner** قبل اللوحات والميزات التشغيلية — **بنية + توثيق فقط، بلا أي ميزة تشغيلية**.
- ترتيب: بعد اعتماد Phase 2 وقبل Phase 3 (بقرار المالك).

### ما نُفّذ
- **Redis:** خدمة `redis:7-alpine` في `docker-compose.yml` (منفذ 6379) + متغيرات env (`REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CHANNEL_LAYER_REDIS_URL`).
- **Cache:** إعداد مركزي — `RedisCache` عند وجود `REDIS_URL`، وإلا `LocMemCache` كـ fallback آمن للتطوير. لا business caching، ولا بيانات حساسة في الكاش.
- **Celery foundation:** `config/celery.py` (Celery app يقرأ إعدادات Django بـ namespace `CELERY` + autodiscover)، مربوط عبر `config/__init__.py`، ومهمة health وحيدة `core.ping` (بلا مهام تشغيلية).
- **Realtime (قرار: Django Channels + Redis Channel Layer):** `config/asgi.py` أصبح `ProtocolTypeRouter` (HTTP=Django, WebSocket=Channels)؛ تطبيق `apps/realtime` بـ consumer وrouting؛ endpoint بنية فقط `ws/health/` (لا events تشغيلية). سبب اختيار Channels موثّق في وثيقة الاستراتيجية.
- **DRF Pagination:** `apps/common/pagination.py` (`DefaultPagination`: page_size=25، `?page_size=`، max=100) كافتراضي لكل list endpoint مستقبلي.
- **Frontend:** نوع `PaginatedResponse<T>` في `types.ts`. بلا صفحات، بلا data fetching، بلا localStorage كمصدر حقيقة.
- **وثائق الأداء:** `docs/PERFORMANCE_AND_REALTIME_STRATEGY.md` (+ قسم Performance Budget) و`docs/DATABASE_INDEX_STRATEGY.md`.
- **التبعيات:** `redis`, `celery`, `channels`, `channels-redis`, `daphne` في `requirements/base.txt`.

**جاهزية الإنتاج على Hetzner (توثيق + أمثلة، بلا نشر فعلي):**
- `docs/HETZNER_PRODUCTION_READINESS.md` (بنية الإنتاج، الدومينات funduqii.com/app./api.، Nginx+SSL، Gunicorn/Daphne، فصل الخدمات، load balancer، rollback، maintenance).
- `docker-compose.prod.example.yml` (طوبولوجيا الإنتاج: backend/ws/worker/frontend/db/redis/nginx؛ **DEBUG=False**، env files منفصلة، **بلا أسرار**).
- أمثلة env للإنتاج: `backend.env.prod.example`, `db.env.prod.example`, `frontend.env.prod.example` (الحقيقية `*.env.prod` محميّة في `.gitignore`).
- `docs/BACKUP_AND_RESTORE_STRATEGY.md` (pg_dump يومي، retention يومي/أسبوعي/شهري، نسخ خارج السيرفر، اختبار restore، runbooks).
- `docs/SECURITY_AND_FIREWALL_CHECKLIST.md` (إغلاق المنافذ، 80/443 فقط، DB/Redis غير عامة، SSH keys، secrets خارج Git، CORS/ALLOWED_HOSTS/HSTS، rate limiting لاحقًا).
- `docs/MONITORING_AND_OBSERVABILITY_STRATEGY.md` (logging منظّم، error tracking، مراقبة CPU/RAM/Disk/DB/Redis/Celery/API، تنبيهات، health checks).
- `docs/MEDIA_AND_OBJECT_STORAGE_STRATEGY.md` (لا صور في DB، object storage، عزل per-hotel، signed URLs، CDN لاحقًا).
- `docs/SCALING_ROADMAP.md` (Stage 1→4: single server → split DB → load balancer → specialized services).
- `docs/PRODUCTION_ENVIRONMENT_MATRIX.md` (جدول development/staging/production).

### الملفات المضافة/المعدّلة (أبرزها)
- جديدة: `config/celery.py`؛ `apps/core/tasks.py`؛ `apps/common/pagination.py`؛ `apps/realtime/{__init__,apps,consumers,routing,tests}.py`؛ `docs/PERFORMANCE_AND_REALTIME_STRATEGY.md`؛ `docs/DATABASE_INDEX_STRATEGY.md`.
- معدّلة: `config/__init__.py` (تحميل celery_app)؛ `config/asgi.py` (ProtocolTypeRouter)؛ `config/settings/base.py` (channels + apps.realtime، CACHES، CELERY، CHANNEL_LAYERS، pagination)؛ `requirements/base.txt`؛ `docker-compose.yml` (+redis)؛ `backend/.env.example` و`.env.example` (متغيرات Redis/Celery/Channels)؛ `apps/core/tests.py` (cache/celery/pagination)؛ `frontend/src/lib/api/types.ts`؛ `README.md`؛ `DEVELOPMENT_RULES.md`.

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check --dry-run` | ✅ No changes detected (لا Models جديدة) |
| `manage.py test` (SQLite) | ✅ **43/43 OK** (شامل WebSocket health + cache + celery task + pagination) |
| Redis حيّ (Docker) + Django cache set/get | ✅ backend=`RedisCache`، المفتاح ظهر في Redis DB0 |
| Celery worker حيّ (`--pool=solo`) + `ping.delay().get()` | ✅ أعاد `pong` عبر Redis broker/result |
| WebSocket `/ws/health/` | ✅ مُختبَر عبر `WebsocketCommunicator` (in-memory layer) داخل السويت |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح |

### ملاحظات وقرارات
- **قرار Realtime:** Django Channels + Redis Channel Layer (WebSockets) بدل SSE — للحاجة إلى دفع لحظي ثنائي الاتجاه ومتعدد العمليات، والتكامل مع Redis وDjango auth. (موثّق في وثيقة الاستراتيجية.)
- أُضيف `daphne` كخادم ASGI (لازم لتقديم WebSockets ولأداة اختبار Channels)؛ **لم يُضَف إلى INSTALLED_APPS** كي يبقى `runserver` على WSGI الافتراضي.
- Redis اختُبِر فعليًا عبر Docker (الحاوية أُوقفت/أُزيلت بعد الاختبار). Docker Desktop كان يعمل من Phase 2.
- لا Models أعمال، لا migrations جديدة.
- **جاهزية Hetzner توثيقية فقط** (لا نشر ولا سيرفر). تم التحقق: لا أسرار حقيقية في أي ملف، و**لا `DEBUG=True`** في مثال الإنتاج، وملفات `*.env.prod` الحقيقية محميّة في `.gitignore`.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- لا Login/Dashboard/لوحات/موقع عام. لا حجوزات/غرف/نزلاء/مال/مطعم/تنظيف/صيانة/مفقودات/ورديات/إغلاق/اشتراكات/تقارير/إشعارات. لا Audit Log كامل. لا مهام Celery تشغيلية، ولا events WebSocket تشغيلية. لا business caching. لا Models أعمال. لا seed data.

### الاعتماد
- **معتمدة من المالك بتاريخ 2026-07-07** (مقبولة). ملاحظات الاعتماد:
  1. قُبِل Redis / Cache foundation.
  2. قُبِل Celery foundation.
  3. قُبِل Django Channels / WebSocket foundation.
  4. قُبِل DRF pagination.
  5. قُبِلت وثائق الأداء والريل‑تايم.
  6. قُبِلت استراتيجية الفهارس.
  7. قُبِلت جاهزية Hetzner production readiness.
  8. قُبِلت backup / restore strategy.
  9. قُبِلت security / firewall checklist.
  10. قُبِلت monitoring / observability strategy.
  11. قُبِلت media / object storage strategy.
  12. قُبِل scaling roadmap.
  13. قُبِلت production environment matrix.
  14. تأكيد عدم وجود ميزات تشغيلية.
  15. تأكيد عدم وجود Models أعمال.
  16. تأكيد عدم وجود Login / Dashboard / لوحات.
  17. تأكيد عدم وجود أسرار حقيقية أو `DEBUG=True` في أمثلة الإنتاج.
  18. فحوصات backend وfrontend ناجحة.
- **لم يُغيَّر وضع Phase 3** — لا تبدأ إلا برسالة Phase 3 الرسمية.

---

## Phase 1.6 — Maps, Messaging & External Integrations Foundation
- الحالة: مكتملة ✅ (معتمدة من المالك)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · تاريخ الاعتماد: 2026-07-07
- الهدف: تجهيز القواعد فقط للخرائط، واتساب الرسمي والرسائل، والتكاملات الخارجية — قبل Phase 3، **بلا أي ميزة تشغيلية أو اتصال خارجي أو رسائل فعلية**.
- ترتيب: بعد اعتماد Phase 1.5 وقبل Phase 3.

### ما نُفّذ
- **وثائق الاستراتيجية:** `docs/MAPS_AND_LOCATION_STRATEGY.md` (تخزين موقع محايد للمزود + اختيار مزود الخرائط + قواعد المفاتيح)، `docs/WHATSAPP_AND_MESSAGING_STRATEGY.md` (واتساب الرسمي فقط، الجمهور، أمثلة الرسائل، قوالب ar/en/tr + variables، consent، حالات الإرسال، retry، عبر Celery)، `docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md` (adapter/provider، مزودون disabled/noop، قواعد timeout/retry/logging/async)، `docs/NOTIFICATION_EVENTS_CATALOG.md` (كتالوج أحداث platform/hotel/guest بحقول audience/channels/priority/timing/consent/whatsapp-suitable).
- **سطح إعدادات محايد (بلا أسرار):** أُضيفت متغيرات `MAP_PROVIDER`/`MESSAGING_PROVIDER`/`WHATSAPP_*`/`MAPBOX_*`/`GOOGLE_MAPS_*`/`DEFAULT_COUNTRY_CODE`/`PLATFORM_SUPPORT_*` في `config/settings/base.py` — كلها افتراضيًا `disabled`/فارغة.
- **app خفيف `apps/integrations`** (بلا Models/migrations/APIs/اتصال خارجي): `constants.py` (مفردات محايدة)، `providers.py` (واجهات `MessagingProvider`/`MapsProvider` + `NoopMessagingProvider`/`NoopMapsProvider` لا ترسل شيئًا)، `config.py` (helpers للحالة)، `registry.py` (اختيار المزود)، `tests.py` (3 اختبارات تُثبت أن كل شيء disabled وأن noop لا يرسل شيئًا).
- **env placeholders** في `backend/.env.example` و`.env.example` و`backend.env.prod.example` (كلها disabled/فارغة، **بلا أسرار**).
- تحديث `README.md`، `DEVELOPMENT_RULES.md` (قسم 13)، و`docs/README.md` (فهرس).

### الملفات المضافة/المعدّلة
- جديدة: `apps/integrations/{__init__,apps,constants,providers,config,registry,tests}.py`؛ `docs/MAPS_AND_LOCATION_STRATEGY.md`؛ `docs/WHATSAPP_AND_MESSAGING_STRATEGY.md`؛ `docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md`؛ `docs/NOTIFICATION_EVENTS_CATALOG.md`.
- معدّلة: `config/settings/base.py` (apps.integrations + سطح الإعدادات)؛ `backend/.env.example` · `.env.example` · `backend.env.prod.example` (placeholders)؛ `README.md`؛ `DEVELOPMENT_RULES.md`؛ `docs/README.md`.

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check --dry-run` | ✅ No changes detected (لا Models) |
| `manage.py test` (SQLite) | ✅ **46/46 OK** (43 السابقة + 3 لـ integrations) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح |

### ملاحظات وقرارات
- **أُنشئ `apps/integrations`** (الخيار الاختياري) لأنه أوضح وأأمن من التوثيق وحده: يثبت أن الافتراضي disabled/noop عبر اختبارات. بلا Models/migrations/APIs/packages خارجية/اتصال خارجي.
- **لا أسرار، لا مفاتيح حقيقية، لا رسائل فعلية، لا اتصال بأي API خارجي** (خرائط/واتساب). القرار: واتساب الرسمي فقط (لا Web automation).
- لم يُغيَّر وضع Phase 3.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- لا إرسال واتساب/رسائل حقيقية، لا اتصال Google Maps/Mapbox/WhatsApp، لا مفاتيح حقيقية. لا صفحة خرائط، لا واجهة إعدادات واتساب/قوالب، لا إشعارات فعلية، لا إعدادات فندق/منصة UI، لا موقع عام، لا حجز/دخول/مغادرة. لا Models أعمال، لا APIs تشغيلية، لا واجهات تشغيلية. لم تبدأ Phase 3.

### الاعتماد
- **معتمدة من المالك بتاريخ 2026-07-07** (مقبولة). ملاحظات الاعتماد:
  1. قُبِلت استراتيجية الخرائط.
  2. قُبِلت استراتيجية واتساب والرسائل.
  3. قُبِلت معمارية التكاملات الخارجية.
  4. قُبِل Notification Events Catalog.
  5. قُبِلت env placeholders لأنها بلا أسرار حقيقية.
  6. قُبِل `apps/integrations` لأنه خفيف وآمن ولا يحتوي Models أو migrations أو APIs.
  7. تأكيد عدم إرسال أي رسالة فعلية.
  8. تأكيد عدم الاتصال بأي API خارجي.
  9. تأكيد عدم وجود مفاتيح أو tokens حقيقية.
  10. تأكيد عدم بناء أي ميزة تشغيلية.
  11. تأكيد عدم إنشاء Models أعمال.
  12. تأكيد عدم إنشاء APIs تشغيلية.
  13. تأكيد عدم بدء Phase 3.
  14. فحوصات backend وfrontend ناجحة.
- **المرحلة التالية Phase 1.7** (قبل Phase 3). **لم يُغيَّر وضع Phase 3** — يبدأ برسالته الرسمية فقط.

---

## Phase 1.7 — Governance, Compliance, QA & Release Foundation
- الحالة: مكتملة ✅ (معتمدة من المالك)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · تاريخ الاعتماد: 2026-07-07
- الهدف: تأسيس قواعد الحوكمة، حماية البيانات، الجودة، الإصدارات، والدعم قبل بناء لوحات المنصة — **توثيق فقط، بلا كود أو ميزات تشغيلية**.
- ترتيب: بعد اعتماد Phase 1.6 وقبل Phase 3.

### ما نُفّذ (8 وثائق استراتيجية)
- `docs/DATA_GOVERNANCE_STRATEGY.md` — ملكية بيانات الفندق، العزل، التصدير، الحذف/التعطيل، الاحتفاظ، بيانات النزلاء، الوثائق/الصور، انتهاء الاشتراك، soft vs hard delete، والمالية تُبطَل لا تُحذف.
- `docs/AUDIT_LOG_STRATEGY.md` — من/ماذا/متى/أي فندق؛ أمثلة (تعديل حجز، إبطال دفعة، تغيير صلاحية، تغيير إعدادات، تفعيل/تعطيل اشتراك)؛ append-only؛ إلزامي في المراحل الحساسة (غير مبني الآن).
- `docs/RATE_LIMITING_AND_ABUSE_PROTECTION.md` — حماية login/booking/messaging/public APIs؛ منع brute force/spam؛ حدود مختلفة لكل endpoint؛ app-layer (DRF throttling + Redis) + edge (Nginx). **بلا تنفيذ فعلي الآن.**
- `docs/FEATURE_FLAGS_STRATEGY.md` — تفعيل/تعطيل ميزات حسب الفندق/الباقة؛ أمثلة (restaurant/whatsapp/reports/public_booking/trial)؛ الفرق بين permission (المستخدم) وfeature flag (الفندق/الباقة)؛ فرض من الباكند.
- `docs/API_VERSIONING_STRATEGY.md` — اعتماد `/api/v1/` لكل APIs مستقبلية؛ endpoints الأساس الحالية تبقى كما هي وتُوثَّق كاستثناء مؤقت؛ backward compatibility وbreaking→v2.
- `docs/QA_AND_TESTING_STRATEGY.md` — unit/API/permission/tenant-isolation/frontend/smoke؛ E2E/perf/security لاحقًا؛ **release checklist** كبوابة قبل النشر.
- `docs/RELEASE_AND_DEPLOYMENT_WORKFLOW.md` — dev/staging/production؛ migrations قبل النشر؛ backup قبل release مهم؛ rollback؛ release notes؛ smoke test؛ الموافقة على النشر وفشله.
- `docs/SUPPORT_AND_INCIDENT_RESPONSE.md` — أنواع البلاغات؛ مستويات low/medium/high/critical مع أمثلة (دخول/حجز/دفع/بطء/واتساب/سيرفر)؛ خطوات الحادث الحرج؛ سجل حوادث لاحقًا.

### الملفات المضافة/المعدّلة
- جديدة: الوثائق الثماني أعلاه في `docs/`.
- معدّلة: `README.md` (banner + قسم Phase 1.7)؛ `DEVELOPMENT_RULES.md` (قسم 14)؛ `docs/README.md` (فهرس)؛ `PROGRESS_LOG.md`.
- **لا تغييرات كود** (لا Models/APIs/إعدادات تشغيلية).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| `manage.py test` (SQLite) | ✅ **46/46 OK** |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح |

### ملاحظات وقرارات
- **قرار API versioning:** كل APIs التشغيلية المستقبلية تحت `/api/v1/`؛ endpoints الأساس الحالية (health/auth/probes) تبقى مؤقتًا وتُوثَّق كاستثناء، وقد تُوحَّد تحت v1 لاحقًا مع aliases.
- **قرار Rate limiting:** توثيق فقط في هذه المرحلة (تجنّبًا للتأثير على endpoints/اختبارات الأساس)؛ يُنفَّذ لكل endpoint في مرحلته.
- توضيح: مفاتيح Phase 1.6 (`MESSAGING_PROVIDER=disabled`...) هي تمكين على مستوى النشر، وليست feature flags لكل فندق.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- لا Audit Log فعلي، لا throttling مبني، لا feature-flag system، لا `/api/v1/` routes، لا CI/CD، لا ticketing. لا صفحات/لوحات/Login/Dashboard. لا حجوزات/غرف/نزلاء/مال/اشتراكات. لا Models أعمال، لا APIs تشغيلية. لم تبدأ Phase 3.

### الاعتماد
- **معتمدة من المالك بتاريخ 2026-07-07** (مقبولة). ملاحظات الاعتماد:
  1. قُبِلت Data Governance Strategy.
  2. قُبِلت Audit Log Strategy.
  3. قُبِلت Rate Limiting & Abuse Protection Strategy.
  4. قُبِلت Feature Flags Strategy.
  5. قُبِلت API Versioning Strategy.
  6. قُبِلت QA & Testing Strategy.
  7. قُبِل Release & Deployment Workflow.
  8. قُبِلت Support & Incident Response Strategy.
  9. تأكيد عدم بناء أي ميزة تشغيلية.
  10. تأكيد عدم إنشاء Models أعمال.
  11. تأكيد عدم إنشاء APIs تشغيلية.
  12. تأكيد عدم إنشاء واجهات أو لوحات.
  13. تأكيد عدم بدء Phase 3.
  14. فحوصات backend وfrontend ناجحة.
- **اكتملت مرحلة التأسيس بالكامل (Phases 0 · 1 · 2 · 1.5 · 1.6 · 1.7).** المرحلة التالية رسميًا: **Phase 3 — Platform Owner Panel basics** — لا تبدأ إلا برسالة Phase 3 الرسمية.

---

## Phase 1.8 — Legacy Reference Insights & Product Enhancements Alignment
- الحالة: مكتملة ✅ (معتمدة من المالك — أُقرّت مع اعتماد بدء Phase 3، 2026-07-07)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · الاعتماد: 2026-07-07
- الهدف: استخلاص الأفكار المفيدة من المرجع القديم (`script1.md`/MVP السابق) وتوثيقها رسميًا وربطها بالمراحل — **بلا نقل كود، بلا Models/APIs/واجهات، بلا تغيير البنية المعتمدة**.
- ترتيب: بعد اعتماد Phase 1.7 وقبل Phase 3.

### ما نُفّذ
- **`docs/LEGACY_REFERENCE_INSIGHTS.md`** — يوضّح أن الملف القديم مرجع أفكار فقط، ولماذا لا نعتمد كوده، والأفكار المأخوذة/المرفوضة، وجدول (الفكرة / Adopt·Adapt·Reject·Later / المرحلة) للأفكار A–O.
- **`docs/PRODUCT_ENHANCEMENT_BACKLOG.md`** — جدول 10 أعمدة (Feature · Description · Source · Priority · Target Phase · Backend? · Frontend? · Realtime? · Security Notes · Status) لـ15 فكرة.
- **ملحق في `PROJECT_BLUEPRINT.md`** بعنوان «Legacy Reference Enhancements Adopted» يربط الأفكار بمراحلها **دون تغيير المراحل الأساسية**.
- **تحديث وثائق قائمة** (بلا تكرار عشوائي): Performance/Realtime (search index، optimistic updates بضوابط، skeleton، realtime topics محمية، activity feed≠audit)، Maps (map view في النتائج + markers + booking link)، Audit (الفرق مع Activity Feed)، Monitoring (Uptime Kuma اختياري + API/frontend/WS health)، Hetzner (Nginx افتراضي، Caddy بديل اختياري)، Security (Argon2، Public IDs/UUID، لا IDs متسلسلة عامة)، QA (اختبارات timeline/booking-token/activity-feed/realtime-isolation لاحقًا).
- **تحديث `DEVELOPMENT_RULES.md`** (قسم 15) و`README.md` (قسم Legacy Reference Usage) و`docs/README.md` (فهرس).

### القرارات (Adopt/Adapt/Reject/Later)
- **Adopt:** Reservation Timeline (P6) · Room Status Model (P5+P10) · Separate op. screens (P7/P8) · Booking token link (P12) · Public map view (P12) · Activity Feed (P13) · Skeleton loading (P3+) · UUID/Public ID (قاعدة تصميم من P4).
- **Adapt:** Optimistic updates بضوابط (UX من P3) · Realtime Topics بأمان (auth/عضوية/صلاحية/عزل) · Uptime Kuma (اختياري).
- **Later:** Search/Meilisearch (index فقط) · Command Palette · Argon2.
- **Reject:** نقل الكود/الأدوار الثابتة/auth القديم/WebSocket غير المعزول/DRF→Ninja/`.env`/`db.sqlite3` · Caddy كأساسي (Nginx يبقى الافتراضي).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| `manage.py test` (SQLite) | ✅ **46/46 OK** |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح |

### ملاحظات وقرارات
- **لا نقل كود** من الملف القديم؛ المشروع الحالي المصدر التقني الوحيد. لا Models/APIs/واجهات، ولا تغيير في المراحل الأساسية (ربط فقط).
- كل فكرة مستقبلية دخلت الـ backlog أولًا، وتخضع لقواعد التطوير عند تنفيذها.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- لا تنفيذ لأي من أفكار الـ backlog (كلها مؤجّلة لمراحلها). لا صفحات/لوحات/Login/Dashboard. لا حجوزات/غرف/نزلاء/مال/اشتراكات. لا Models أعمال، لا APIs تشغيلية. لم تبدأ Phase 3.

### الاعتماد
- لم تُعتمد ذاتيًا. بانتظار مراجعة المالك واعتماده. **لم يُغيَّر وضع Phase 3.**

---

## Phase 3 — Platform Owner Panel basics
- الحالة: مكتملة ✅ (معتمدة من المالك رسميًا عبر PR #1)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · الاعتماد: 2026-07-07
- الهدف: بناء الأساس الأول **للوحة صاحب المنصة فقط** — دخول آمن، App Shell مركزي، لوحة أولية، إدارة الفنادق كـ tenants (محدود)، الباقات، اشتراكات الفنادق، إعدادات منصة أساسية — تحت `/api/v1/platform/` ومحميّة بـ `IsPlatformOwner`.
- ترتيب: أول مرحلة ميزات حقيقية، بعد اعتماد كل مراحل التأسيس (0/1/1.5/1.6/1.7/1.8/2).

### ما نُفّذ (Backend)
- **تطبيق `apps.subscriptions`** — أول Models أعمال: `SubscriptionPlan` (باقة قابلة للبيع) و`HotelSubscription` (اشتراك فندق). قيد قاعدة بيانات: **اشتراك حيّ واحد فقط لكل فندق** (`UniqueConstraint` على `hotel` بشرط `status ∈ {trial, active, past_due}`). خدمات lifecycle داخل transactions: `start_trial` (تجربة مرة واحدة)، `activate_subscription` (تفعيل مدفوع + ترقية التجربة)، `cancel`/`expire`.
- **تطبيق `apps.platform`** (label `platform_owner`) — طبقة API لصاحب المنصة: `PlatformSettings` (Singleton pk=1)، Serializers (DRF `ModelSerializer` — أول استخدام)، Views (generics + APIView) كلها بـ `permission_classes=[IsPlatformOwner]`، خدمة `create_hotel` + `set_primary_manager`.
- **URLs** تحت `/api/v1/platform/`: `overview/`، `hotels/`(+`{id}/`، +`{id}/manager/`)، `plans/`(+`{id}/`)، `subscriptions/`(+`{id}/`)، `settings/`.
- **قاعدة التجربة المجانية مرة واحدة** مُنفَّذة: `hotel_has_used_trial` يفحص وجود أي اشتراك سبق أن كان تجربة (عبر `trial_ends_at`)، فلا تُعاد بعد انتهائها.
- **حماية حذف الباقة المستخدَمة**: `perform_destroy` يرفض الحذف بـ 409 `plan_in_use` إن كانت مرتبطة باشتراكات (+ `on_delete=PROTECT` كخط دفاع ثانٍ).

### ما نُفّذ (Frontend)
- **نظام i18n مركزي فعّال**: `I18nProvider` (client context) + قواميس ar/en/tr مكتملة (نوع `Dictionary` مشتق من الإنجليزية → أي مفتاح ناقص = خطأ بناء)، تبديل لغة فوري مع RTL/LTR، وقراءة اللغة من كوكي في الـ root layout (بلا وميض).
- **جلسة آمنة (BFF)**: تسجيل الدخول عبر Next route handlers يخزّن JWT في **HttpOnly Secure cookies** — **لا localStorage إطلاقًا**. Proxy مصادَق (`/api/platform/[...]`) يرفق التوكن من الكوكي مع تجديد تلقائي عند 401 (يحفظ التوكن المُدوَّر). `proxy.ts` (middleware) + gate في `platform/layout.tsx` (تحقق owner من الخادم).
- **App Shell مركزي**: `AppShell`/`Sidebar`/`Topbar`/`ContentContainer`/`PageContainer` + Language switcher + Logout + حالة المستخدم، sidebar متجاوب (drawer على الشاشات الصغيرة).
- **مكتبة مكونات مركزية** على design tokens: Button/IconButton/Card/StatCard/Badge/Input/Select/Textarea/Switch/PasswordInput/Modal/ConfirmDialog/DataTable/EmptyState/LoadingState/ErrorState/PageHeader/SectionHeader/FilterBar/Pagination/FormField/Alert/Toast.
- **صفحات**: `/login`، `/platform` (Dashboard)، `/platform/hotels`، `/platform/hotels/[id]`، `/platform/plans`، `/platform/subscriptions`، `/platform/settings`. حالات loading/empty/error موحّدة في كل مكان.

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| `manage.py test` (SQLite) | ✅ **82/82 OK** (46 سابقة + 36 جديدة لـ subscriptions/platform) |
| فحص حيّ End-to-End (Django+Next) | ✅ login (HttpOnly cookies) · proxy overview/plans/hotels · trial ثم رفض التكرار 409 · unauth 401 · non-owner 403 · `/platform` بلا كوكي → 307 `/login` · تجديد التوكن التلقائي عند 401 |
| Frontend `lint` | ✅ exit 0 |
| Frontend `tsc --noEmit` | ✅ لا أخطاء أنواع |
| Frontend `build` | ✅ نجح (14 مسار + Proxy) |

### ملاحظات وقرارات معمارية
- **جلسة الكوكيز (BFF)**: قرار مقصود لتلبية «لا JWT في localStorage». Next route handlers هي الطبقة الوحيدة التي تقرأ/تكتب كوكيز التوكن؛ التجديد (مع تدوير refresh) يحدث فقط داخل route handlers ليُحفظ التوكن المُدوَّر دائمًا.
- **DRF `ModelSerializer`**: أُدخل هنا (أول CRUD حقيقي) بدل دوال الـ dict اليدوية في Phase 2 — للتحقّق و partial updates وأظرف الأخطاء الموحّدة.
- **تعطيل قاعدة lint واحدة** `react-hooks/set-state-in-effect` (heuristic من React 19) لأنها تعلّم أنماط جلب البيانات عند التحميل وإعادة ضبط نماذج المودال عند الفتح — وهي استخدامات صحيحة للـ effects؛ بقية قواعد react-hooks فعّالة. موثّق في `eslint.config.mjs`.
- **بدون action log**: لم يُبنَ (اختياري في نطاق المرحلة) — مؤجّل لمرحلة التقارير/التدقيق.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا لوحة فندق، لا موقع عام، لا حجوزات/غرف/طوابق/نزلاء/دخول/مغادرة/مال/فوليو/فواتير/مطعم/تنظيف/صيانة/ورديات/إغلاق يومي/تقارير تشغيلية.**
- **لا إرسال فعلي**: لا واتساب، لا بريد، لا خرائط، لا Meilisearch، لا Command Palette/Activity Feed/Reservation Timeline.
- **لا دفع إلكتروني/بوابة/فواتير اشتراك/تحصيل**. إعدادات المنصة أساسية فقط (لا إعدادات موقع عام/SEO/مفاتيح حقيقية).
- إدارة الفنادق **tenant-only** (name/slug/status + مدير رئيسي) — بلا إعدادات فندق تفصيلية/صور/خرائط.

### الاعتماد
- **معتمدة رسميًا من المالك بتاريخ 2026-07-07** عبر مراجعة PR #1 (بعد تصحيح ملاحظة README التوثيقية). الحالة: **مكتملة ✅**.

#### ملاحظات الاعتماد (من المالك)
1. تم قبول Platform Owner Panel basics.
2. تم قبول Login UI.
3. تم قبول Platform App Shell.
4. تم قبول Platform Dashboard.
5. تم قبول Hotels-as-tenants management المحدودة.
6. تم قبول Subscription Plans.
7. تم قبول Hotel Subscriptions.
8. تم قبول Basic Platform Settings.
9. تم قبول أن كل APIs التشغيلية الجديدة تحت `/api/v1/platform/`.
10. تم قبول حماية APIs بصلاحية Platform Owner.
11. تم قبول منع hotel users وغير المصادقين.
12. تم قبول الالتزام بالواجهة المركزية والترجمة ar/en/tr وRTL/LTR.
13. تم قبول أن الواجهة متجاوبة وتعتمد components مركزية.
14. تم التأكد من عدم بناء لوحة الفندق.
15. تم التأكد من عدم بناء الموقع العام.
16. تم التأكد من عدم بناء الحجوزات أو الغرف أو النزلاء أو المال.
17. تم التأكد من عدم إرسال واتساب أو خرائط فعلية.
18. تم تصحيح README وإزالة التناقض القديم.
19. فحوصات backend ناجحة: 82/82.
20. فحوصات frontend lint/typecheck/build ناجحة.

---

## Phase 3.1 — Premium UI Design System & Visual Polish
- الحالة: مكتملة ✅ (معتمدة من المالك مبدئيًا وتشغيليًا عبر PR #2)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · الاعتماد: 2026-07-07
- **ملاحظة اعتماد:** تم اعتماد Phase 3.1 مبدئيًا وتشغيليًا، مع تأجيل أي refinements بصرية إضافية إلى مرحلة نهائية لاحقة بعد اكتمال باقي الواجهات (مرحلة قادمة باسم قريب من **Final Visual Identity & UI Refinement Pass** تراجع الألوان والهوية البصرية والفخامة واللمسات النهائية والموبايل والجداول والنماذج والصور وتجربة المستخدم والتناسق بين كل الصفحات).
- الهدف: رفع جودة واجهات Phase 3 إلى مستوى **Premium SaaS** وتثبيت نظام تصميم مركزي (tokens + أيقونات + مكوّنات + حركة + responsive + RTL) لكل المراحل القادمة. **UI polish فقط** — بلا ميزات، بلا Models، بلا APIs تشغيلية، بلا تغيير business logic.

### ما نُفّذ
- **Design tokens مركزية مُطوّرة** (`styles/tokens.css`): لوحة teal فاخرة هادئة، طبقات خلفيات/أسطح، حدود، ألوان نص/muted، feedback + soft، مقياس مسافات/radius/shadow/typography، focus ring، transitions/easing، أحجام أيقونات، z-index. لا قيم عشوائية في الصفحات.
- **نظام أيقونات مركزي واحد**: `lucide-react` عبر مكوّن `Icon` مركزي (توحيد الحجم + stroke 1.75). **أُزيلت كل الإيموجي** من الواجهة (☰ → Menu، × → X، إلخ). أيقونات في Sidebar وstat cards والأزرار وempty/error states والتنبيهات وإظهار كلمة المرور والـ pagination ومبدّل اللغة.
- **مكتبة مكوّنات محسّنة**: Button (icon + loading)، IconButton، StatCard (icon chip + tone)، Badge، Inputs/Select (chevron مخصّص RTL-aware)/Textarea/Switch/PasswordInput (Eye/EyeOff)، Modal (fade+scale + X)، ConfirmDialog، DataTable، Pagination (chevrons تنعكس RTL)، FilterBar، FormField، Alert (أيقونة حسب النوع)، Toast (slide)، **Skeleton** جديد، وحالات loading/empty/error بأيقونات دائرية.
- **AppShell/Sidebar/Topbar Premium**: brand mark، nav بأيقونات + active pill بشريط accent (inline-start)، topbar شفاف لاصق + avatar بالأحرف الأولى + هوية المستخدم، drawer متجاوب على ≤900px مع overlay.
- **Login Premium**: brand mark، خلفية radial هادئة، card بظل، حالة loading على الزر.
- **Dashboard Premium**: stat cards بأيقونات + tones، **loading skeleton** يحاكي التخطيط، empty states.
- **Motion**: transitions موحّدة + fade/scale/slide/shimmer، مع احترام `prefers-reduced-motion` عالميًا.

### الملفات
- **جديدة:** `components/ui/Icon.tsx` · `components/ui/Skeleton.tsx` · `docs/PREMIUM_UI_DESIGN_SYSTEM.md`.
- **معدّلة (تصميم فقط):** `styles/tokens.css` · `styles/globals.css` · كل مكوّنات `components/ui/*` وlayout ذات الصلة · صفحات `login` و`platform/*` (أيقونات + skeletons + classes، بلا تغيير منطق) · `package.json` (+lucide-react) · `eslint.config.mjs` (كما هو) · التوثيق (README, DEVELOPMENT_RULES §16, docs/README, FRONTEND_DESIGN_SYSTEM_GUIDELINES).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| Frontend `lint` | ✅ exit 0 |
| Frontend `tsc --noEmit` | ✅ لا أخطاء أنواع |
| Frontend `build` | ✅ نجح (14 مسار + Proxy) |
| `manage.py check` | ✅ لا مشاكل |
| `manage.py test` | ✅ **82/82 OK** (لا تغيير backend) |
| فحص بصري حيّ (Playwright، Chromium) | ✅ login/dashboard/hotels/plans بالإنجليزية والعربية + موبايل — Premium، RTL سليم، responsive، بلا كسر جداول، بلا إيموجي |

### ملاحظات وقرارات
- لا Models جديدة، لا APIs تشغيلية، لا تغيير في business logic أو قواعد الاشتراكات/الصلاحيات. الباكند لم يُلمس (الفحوصات للتأكد فقط).
- أُضيفت مكتبة خفيفة واحدة `lucide-react` كنظام أيقونات معتمد (مسموح صراحةً في نطاق المرحلة).
- كل النصوص من قواميس الترجمة المركزية (ar/en/tr)؛ لا نصوص hardcoded؛ RTL/LTR عبر logical properties.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا ميزات جديدة**، لا لوحة فندق/موقع عام/غرف/حجوزات/نزلاء/مال/خرائط/واتساب فعلي، لا Models، لا APIs تشغيلية، لم تبدأ Phase 4.

### جولة تحسين بصري ثانية (بطلب المالك — مراجعة بصرية 2026-07-07)
بعد المراجعة البصرية الأولى رأى المالك أن التنفيذ نظيف لكنه لم يبلغ مستوى Premium المطلوب لهوية Funduqii. نُفّذ **رفع بصري قوي داخل نفس المرحلة ونفس PR** (بلا أي تغيير منطقي):
- **هوية بصرية أعمق في tokens:** teal عميق + accent بحري/emerald + خلفيات warm neutral + تدرجات هادئة (`--gradient-brand/-hero/-surface`) + ظلال brand مموّهة + مقاييس typography أقوى (حتى 4xl، extrabold، tracking).
- **Login إعادة تصميم:** لوحتان — panel جانبي فاخر (gradient hero + نمط نقاط + brand mark + عنوان + 3 مزايا) وكرت دخول أرقى (brand mark أكبر، زر gradient، حقول أنعم).
- **AppShell:** brand block أقوى بفاصل، active nav بحبّة gradient مملوءة + ظل، **بطاقة مستخدم أسفل الـ sidebar** (avatar + اسم + بريد)، topbar فيه scope label + فاصل + logout (لم يعد فارغًا).
- **Dashboard:** **hero ترحيبي** (gradient + eyebrow + «Welcome back, {name}» + subtitle + glass mark)، stat cards أقوى (رقم بارز + icon chip مموّه للأساسي + caption وصفي صادق)، section headers بأيقونات chip.
- **Settings:** كل قسم بطاقة premium (icon + عنوان + وصف) بمسافات أوضح.
- **Tables/Forms/States:** أسطح أنعم، hover بلون العلامة، badges بحدود، modals 2xl مع blur، empty states مصممة داخل بطاقة، أزرار gradient.
- **مفاتيح ترجمة جديدة** (ar/en/tr) لكل النصوص المضافة (aside، welcome، captions، أوصاف الأقسام) — لا hardcoded.
- **لقطات جديدة** التُقطت عبر Playwright/Chromium لكل الصفحات المطلوبة (login/dashboard/settings/hotels/plans بالإنجليزية والعربية + موبايل + drawer + empty + modal) وأُرسلت للمالك للمراجعة البصرية.
- **الفحوصات بعد الجولة الثانية:** frontend lint/tsc/build ✅ · backend check + **82/82** ✅ (الباكند لم يُلمس).

### الاعتماد
- **معتمدة من المالك بتاريخ 2026-07-07** (مبدئيًا وتشغيليًا) عبر مراجعة PR #2، مع تأجيل أي تحسينات بصرية إضافية إلى مرحلة **Final Visual Identity & UI Refinement Pass** لاحقًا. الحالة: **مكتملة ✅**. **لم يُغيَّر وضع Phase 4** — يبدأ برسالته الرسمية فقط.

---

## Phase 4 — Hotels + Hotel Settings
- الحالة: مكتملة ✅ (معتمدة من المالك رسميًا عبر PR #3)
- التاريخ: بدأت 2026-07-07 · اكتمل التنفيذ 2026-07-07 · الاعتماد: 2026-07-07
- الهدف: بناء **إعدادات الفندق ووسائطه فقط** (الهوية/التواصل/الموقع/السياسات/الإعدادات الافتراضية + الشعار/الغلاف/المعرض) وربطها بالـ tenant (Phase 3)، تحت `/api/v1/hotel/` بعزل tenant وصلاحيات كاملة. **ليست مرحلة تشغيل الفندق** — لا غرف/طوابق/حجوزات/نزلاء/مال/موقع عام.

### ما نُفّذ (Backend)
- **تطبيق `apps/hotels`** منفصل عن `tenancy` (الذي يبقى tenant minimal): 
  - **`HotelSettings`** (OneToOne مع `tenancy.Hotel`، يُنشأ تلقائيًا عند أول قراءة) — Identity/Contact/Location/Policies/Operational-defaults. حقول الخرائط/واتساب **قيم فقط** (لا اتصال).
  - **`HotelMedia`** — صور logo/cover/gallery كملفّات storage (لا DB، لا base64)، مع قيود قاعدة بيانات: **شعار نشط واحد + غلاف نشط واحد** لكل فندق.
- **تحقّق صور دفاعي متعدد الطبقات** (`validators.py`): امتداد + content-type + magic bytes، **رفض SVG**، وحدود حجم/عدد قابلة للتهيئة من env (logo≤1MB · cover≤5MB · gallery≤5MB لكل صورة · ≤10 صور).
- **خدمات آمنة** (`services.py`): الاستبدال يتحقّق أولًا ثم يعطّل القديم وينشئ الجديد داخل transaction (لا يُحذف القديم قبل نجاح الجديد)؛ حدّ المعرض؛ حذف يزيل الملف.
- **APIs تحت `/api/v1/hotel/`**: `settings/`(GET/PATCH) · `profile/`(GET) · `media/`(GET/POST multipart) · `media/{id}/`(PATCH metadata/DELETE) — **النصوص والصور منفصلة تمامًا**.
- **صلاحيات وعزل**: كل endpoint يستخدم `HasHotelPermission("settings.view"/"settings.update")` (المسجّلة أصلًا) → JWT + عضوية نشطة + X-Hotel-ID + الصلاحية. الفندق المعلّق **للقراءة فقط** (`403 hotel_suspended` عند التعديل). أخطاء موحّدة جديدة: `hotel_suspended`, `invalid_media_file`, `media_limit_reached`.

### ما نُفّذ (Frontend)
- **جلسة جانب الفندق (BFF)**: تسجيل الدخول يوجّه حسب النوع — مالك المنصة → `/platform`، مستخدم فندق بعضوية نشطة → `/hotel` (يُخزَّن معرّف الفندق في **كوكي HttpOnly** ويُرفق كـ `X-Hotel-ID` عبر proxy `/api/hotel/[...]` الذي يمرّر multipart للرفع). لا توكن/معرّف فندق في JS.
- **Hotel AppShell محدود** (نفس نظام التصميم Premium عبر `variant`): sidebar باسم الفندق + عضو، topbar، صفحة **`/hotel/settings`** فقط (و`/hotel` → redirect).
- **صفحة إعدادات احترافية**: أقسام (الهوية/التواصل/الموقع/السياسات/الإعدادات الافتراضية/الهوية البصرية)، حفظ نصّي واحد + **إدارة وسائط منفصلة** (رفع/استبدال logo وcover، معرض برفع/حذف/إعادة ترتيب up-down)، حالات loading/empty/error/success، confirm dialog للحذف، وضع read-only عند التعليق.
- ترجمات ar/en/tr كاملة لكل نصوص القسم، RTL/LTR، responsive.

### الملفات
- **جديدة (Backend):** `apps/hotels/{__init__,apps,models,validators,services,serializers,views,urls,tests}.py` + migration.
- **جديدة (Frontend):** `app/api/hotel/[...path]/route.ts` · `app/hotel/{layout,page}.tsx` · `app/hotel/settings/page.tsx` · `components/hotel/HotelMediaSection.tsx` · `lib/api/hotel.ts` · `lib/session/CurrentUserContext.tsx` (سابقًا) — والوثيقة `docs/HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md`.
- **معدّلة:** `config/settings/base.py` (+app +حدود media) · `config/urls.py` (+`/api/v1/hotel/` +خدمة media في dev) · `apps/common/exceptions.py` (أخطاء Phase 4) · Frontend: `session/{config,server}.ts`, `api/session/login`/`refresh` routes, `proxy.ts`, `api/{types,errors}.ts`, `components/layout/{AppShell,Sidebar,Topbar}.tsx`, `app/login/page.tsx`, قواميس ar/en/tr، `styles/globals.css` (media) + التوثيق (README, DEVELOPMENT_RULES §8a, docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **110/110 OK** (82 سابقة + 28 لـ hotels) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/settings` مبني) |
| فحص حيّ End-to-End (Django+Next، رفع media فعلي) | ✅ دخول مدير فندق → `/hotel` + كوكي HttpOnly · GET/PATCH settings · رفع logo (multipart، URL بلا base64) · شعار نشط واحد · **PATCH نصّي لا يلمس الصور** · رفض SVG (400) · unauth 401 · لقطات `/hotel/settings` EN/AR/موبايل Premium وRTL سليم |

### ملاحظات وقرارات
- media list بلا pagination (مجموعة صغيرة محدودة) لإرجاع قائمة مباشرة.
- بلا Pillow — تحقّق الصور عبر التوقيع/الامتداد/الحجم يكفي ويتجنّب اعتمادية ثقيلة.
- لم تُكسَر صفحات Phase 3؛ AppShell/Sidebar أُعيد تعميمها عبر `variant` دون تغيير سلوك لوحة المنصة.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا غرف/طوابق/أنواع غرف/حجوزات/توفر/نزلاء/دخول-مغادرة/مدفوعات/مصروفات/فوليو/فواتير/مطعم/تنظيف/صيانة/ورديات/إغلاق يومي/تقارير.** لا موقع عام/حجز عام. لا تكامل خرائط/واتساب فعلي، لا Search/Activity Feed/Command Palette. لم تبدأ Phase 5.

### الاعتماد
- **معتمدة من المالك بتاريخ 2026-07-07** (فنيًا ومقبولة) عبر مراجعة PR #3. الحالة: **مكتملة ✅**. **لم يُغيَّر وضع Phase 5** — يبدأ برسالته الرسمية فقط.

#### ملاحظات الاعتماد (من المالك)
1. قبول إنشاء `apps/hotels` وفصل إعدادات الفندق عن `tenancy`.
2. قبول `HotelSettings` كإعدادات فندق OneToOne مع tenant.
3. قبول `HotelMedia` للـ logo / cover / gallery.
4. قبول فصل إعدادات النصوص عن الصور.
5. قبول endpoints تحت `/api/v1/hotel/`.
6. قبول حماية endpoints بالمصادقة والعضوية والصلاحيات.
7. قبول استخدام `settings.view` و`settings.update`.
8. قبول منع وصول مستخدم فندق إلى فندق آخر.
9. قبول أن Platform Owner ليس hotel member تلقائيًا.
10. قبول read-only للفندق المعلّق ومنع الكتابة برسالة واضحة.
11. قبول قواعد الصور: النوع، الحجم، gallery limit، وعدم base64.
12. قبول عدم لمس الصور عند PATCH نصّي للإعدادات.
13. قبول frontend `/hotel/settings` فقط ضمن نطاق Phase 4.
14. قبول الترجمة ar/en/tr وRTL/LTR والـ responsive.
15. قبول عدم بناء غرف أو حجوزات أو نزلاء أو مال.
16. قبول عدم تنفيذ خرائط أو واتساب فعلي.
17. قبول عدم بدء Phase 5.
18. فحوصات backend ناجحة: 110/110.
19. فحوصات frontend lint/typecheck/build ناجحة.

---

## Phase 5 — Floors + Room Types + Rooms
- الحالة: **مكتملة ✅** (معتمدة ومقبولة فنيًا من المالك)
- التاريخ: بدأت 2026-07-07 · اكتملت (تنفيذ) 2026-07-07 · **اعتُمدت 2026-07-07**
- الهدف: أول مرحلة تشغيلية — **المخزون الفيزيائي للفندق** (طوابق + أنواع غرف + غرف بحالة يدوية أساسية)، **بلا** حجوزات/توفر/نزلاء/مال.

### ما نُفّذ (Backend)
- **تطبيق `apps/rooms`** منفصل عن `apps/hotels`، بأربعة نماذج مربوطة بالـ tenant (`hotel` FK):
  - **`Floor`** (طابق/جناح): name/number/description/sort_order/is_active.
  - **`RoomType`** (نوع غرفة): name/code/description/base_capacity/max_capacity/bed_type/amenities(JSON)/base_rate(قيمة مرجعية فقط، لا فوترة)/is_active/sort_order — **قيد فريد `(hotel, code)`**.
  - **`Room`** (غرفة فعلية): floor(**PROTECT**)/room_type(**PROTECT**)/number/display_name/status/status_note/status_changed_at/status_changed_by/is_active — **قيد فريد `(hotel, number)`**.
  - **`RoomStatusLog`**: سجلّ حالة الغرفة فقط (previous/new/note/changed_by) — ليس audit log عام.
- **حالة الغرفة يدوية تشغيلية فقط**: `available/dirty/cleaning/maintenance/out_of_service/archived`. **لا `reserved`/`occupied`** (مشتقّة من النظام لاحقًا في Phase 6/7).
- **قواعد العمل**: عزل tenant صارم؛ floor + room_type لغرفة **يجب** أن ينتميا لنفس الفندق (وإلا `400 cross_tenant_reference`)؛ رقم الغرفة/كود النوع فريد لكل فندق؛ تحقّق السعة (`max ≥ base` وكلاهما موجب)؛ **لا يُحذف** طابق/نوع فيه غرف (`409 resource_in_use` → عطِّله بدل الحذف)؛ تغييرات الحالة عبر مسار خدمة واحد داخل transaction مع تسجيل + **ملاحظة إلزامية** لـ maintenance/out_of_service (`400 status_note_required`)؛ `archived` مخفية افتراضيًا.
- **صلاحيات في السجلّ**: `rooms.view/create/update/delete/status_update` — مفروضة على الباكند لكل endpoint عبر `HasHotelPermission`. الفندق المعلّق **للقراءة فقط** (`403 hotel_suspended` عند أي كتابة).
- **APIs تحت `/api/v1/hotel/`**: `floors/`+`floors/{id}/` · `room-types/`+`room-types/{id}/` · `rooms/`+`rooms/{id}/` (فلاتر: floor/type/status/is_active/search/include_archived) · `rooms/{id}/status/`.
- أخطاء موحّدة جديدة: `resource_in_use` (409) · `cross_tenant_reference` (400) · `status_note_required` (400).

### ما نُفّذ (Frontend)
- **عنصر «الغرف»** في sidebar الفندق، وصفحة **`/hotel/rooms`** بتبويبات: نظرة عامة / الطوابق / أنواع الغرف / الغرف.
- **نظرة عامة**: بطاقات ملخّص الحالات. **الطوابق/الأنواع**: جداول + إنشاء/تعديل/حذف مع confirm dialogs. **الغرف**: شبكة بطاقات بألوان لكل حالة + شارات، فلاتر (طابق/نوع/حالة/بحث + إظهار المؤرشفة)، CRUD، ونافذة تغيير حالة (حقل ملاحظة يظهر للحالات التي تتطلبها).
- نظام التصميم المركزي + أيقونات lucide، ترجمات **ar/en/tr** كاملة مع RTL/LTR، حالات loading/empty/error/success، responsive حقيقي.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/rooms/{__init__,apps,models,services,serializers,views,urls,tests}.py` + migration.
- **جديدة (Frontend):** `app/hotel/rooms/page.tsx` · `components/hotel/rooms/{OverviewTab,FloorsTab,RoomTypesTab,RoomsTab,index}.tsx` · `components/ui/Tabs.tsx` · `lib/api/{hotelFetch,rooms}.ts` · والوثيقة `docs/FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md`.
- **معدّلة (Backend):** `apps/rbac/registry.py` (+delete/status_update) · `apps/common/exceptions.py` (3 أخطاء) · `config/settings/base.py` (+app) · `config/urls.py` (+urls) · `apps/hotels/tests.py` (تحديث اختبار regression للنماذج غير المسموحة).
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `components/ui/index.ts` · `lib/api/{hotel,types,errors}.ts` · `lib/format.ts` · قواميس ar/en/tr · `styles/globals.css` · التوثيق (README, DEVELOPMENT_RULES §8b, docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **140/140 OK** (110 سابقة + 30 لـ rooms) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/rooms` مبني) |
| فحص حيّ End-to-End (Django+Next) | ✅ دخول مدير فندق → إنشاء طابق + نوع STD + غرف 101/102/103 · تغيير 102→dirty، 103→maintenance بملاحظة · maintenance بلا ملاحظة → **400** · قائمة الغرف بالفلاتر · لقطات `/hotel/rooms` overview/EN/AR/موبايل Premium وRTL سليم |

### ملاحظات وقرارات
- `base_rate` قيمة مرجعية فقط — Phase 5 لا يبني تسعيرًا/فوترة.
- `PROTECT` على floor/room_type في `Room` خط دفاع ثانٍ خلف فحص «لا حذف أثناء الاستخدام».
- قوائم الطوابق/الأنواع/الغرف مرقّمة (paginated) والواجهة تقرأ `.results`.
- تحديث اختبار regression في Phase 4 ليمنع فقط نماذج (reservations/guests/invoices/folios/payments) — جداول rooms/floors أصبحت مشروعة في Phase 5.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا حجوزات/توفر/نزلاء/دخول-مغادرة/مدفوعات/مصروفات/فوليو/فواتير/مطعم/تنظيف-صيانة (workflows)/ورديات/إغلاق يومي/تقارير.** لا موقع عام/حجز عام. لا حالتَي `reserved`/`occupied`. **لم تبدأ Phase 6.**

### الاعتماد
- **معتمدة ومقبولة فنيًا من المالك بتاريخ 2026-07-07** عبر مراجعة PR #4. الحالة: **مكتملة ✅**. **لم يُغيَّر وضع Phase 6** — يبدأ برسالته الرسمية فقط.

#### ملاحظات الاعتماد (من المالك)
1. قبول إنشاء app مستقل `apps/rooms`.
2. قبول فصل الغرف والطوابق وأنواع الغرف عن `apps/hotels`.
3. قبول Model `Floor`.
4. قبول Model `RoomType`.
5. قبول Model `Room`.
6. قبول Model `RoomStatusLog` كسجلّ حالة غرفة فقط، وليس audit log عام.
7. قبول حالات الغرف اليدوية: `available` · `dirty` · `cleaning` · `maintenance` · `out_of_service` · `archived`.
8. قبول عدم إضافة `reserved`/`occupied` لأنها ستُشتق لاحقًا من الحجوزات وcheck-in/check-out.
9. قبول صلاحيات: `rooms.view` · `rooms.create` · `rooms.update` · `rooms.delete` · `rooms.status_update`.
10. قبول tenant isolation.
11. قبول منع cross-tenant floor/room_type references.
12. قبول unique room number داخل الفندق.
13. قبول unique room type code داخل الفندق.
14. قبول capacity validation.
15. قبول منع حذف floor/room type مستخدم.
16. قبول إلزام الملاحظة لحالات `maintenance` و`out_of_service`.
17. قبول إخفاء `archived` افتراضيًا.
18. قبول read-only للفندق المعلّق ومنع الكتابة.
19. قبول APIs تحت `/api/v1/hotel/`.
20. قبول صفحة `/hotel/rooms`.
21. قبول تبويبات: Overview · Floors · Room Types · Rooms.
22. قبول الترجمة ar/en/tr.
23. قبول RTL/LTR والـ responsive.
24. قبول عدم بناء حجوزات أو محرك توفر.
25. قبول عدم بناء نزلاء أو مال أو تنظيف/صيانة workflows.
26. فحوصات backend ناجحة: 140/140.
27. فحوصات frontend lint/typecheck/build ناجحة.

#### ملاحظة مستقبلية
- قبل الإنتاج/الإطلاق النهائي: فحص أوسع على PostgreSQL وبيانات أكبر للتأكد من الأداء والفلاتر وpagination وسلامة العلاقات. لا يمنع اعتماد Phase 5 الآن.

---

## Phase 6 — Reservations + Availability Engine
- الحالة: **مكتملة ✅** (معتمدة ومقبولة فنيًا من المالك — تشمل التصحيح Phase 6.1)
- التاريخ: بدأت 2026-07-07 · اكتملت (تنفيذ) 2026-07-07 · **اعتُمدت 2026-07-07**
- الهدف: نظام الحجوزات الداخلي للفندق + **محرك توفر مركزي يمنع overbooking**، **بلا** check-in/out ولا نزلاء كاملين ولا مال ولا موقع عام.
- **ملاحظة الاعتماد:** «تم اعتماد Phase 6 بعد تنفيذ Phase 6.1 لدعم تعيين غرفة محددة داخل الحجز، مع منع تضارب نفس الغرفة ودعم assigned/unassigned availability. لا تشمل هذه المرحلة check-in/check-out أو Guest module كامل أو payments/folio/invoices أو public booking.»

### ما نُفّذ (Backend)
- **تطبيق مستقل `apps/reservations`** (منفصل عن rooms/hotels)، بثلاثة نماذج مربوطة بالـ tenant:
  - **`Reservation`** (رأس الحجز): `reservation_number` (**فريد لكل فندق**، تسلسل مستقل `R00001…`)، `status`، `source`، `check_in_date`/`check_out_date` (قيد `check_out > check_in`)، **snapshot ضيف رئيسي** (name مطلوب/phone/email — **لا Guest profile**)، adults/children/notes/special_requests، حقول الإلغاء، `hold_expires_at`، created_by/updated_by؛ `nights`/`total_guests` properties.
  - **`ReservationRoomLine`**: `room_type` (**PROTECT**) + `quantity>0` (+adults/children/notes) — الحجز **حسب نوع الغرفة والكمية**.
  - **`ReservationStatusLog`**: سجلّ حالة الحجز فقط (النموذج المفضّل، نُفِّذ) — ليس audit log عام.
- **حالات الحجز**: `held`/`confirmed`/`cancelled`/`expired`. **لا `checked_in`/`checked_out`/`occupied`/`no_show`** (مؤجّلة لـ Phase 7).
- **محرك التوفر `AvailabilityService`** (مركزي، لا يُكرَّر في serializers/views):
  - **قاعدة التداخل نصف-مفتوحة** `[in, out)` → back-to-back **مسموح**، والتداخل الفعلي **ممنوع**.
  - **ما يحجز المخزون**: `confirmed` + `held` غير المنتهي فقط؛ cancelled/expired والـ held المنتهي **لا يحجزان** (انتهاء الحجز المؤقت **lazy** بلا Celery).
  - **حساب المخزون** من Phase 5: غرف active + طابق active + نوع active وليست maintenance/out_of_service/archived. **قرار موثّق:** dirty/cleaning تُحتسب ضمن المخزون.
  - **منع overbooking** داخل transaction مع `select_for_update` على أنواع الغرف بترتيب ثابت ثم إعادة حساب التوفر → `409 no_availability`. **الباكند مصدر الحقيقة.**
  - **إعادة الفحص عند التعديل/التأكيد** مع استثناء الحجز نفسه من الحساب.
- **صلاحيات**: `reservations.view/create/update/confirm/cancel` + `availability.view` (و`reservations.assign_room` محجوزة لـ Phase 7). مفروضة على الباكند لكل endpoint. الفندق المعلّق للقراءة فقط. **لا hard-delete** — الإلغاء (بسبب إلزامي) هو المسار.
- **APIs تحت `/api/v1/hotel/`**: `reservations/`(+overview/) · `reservations/{id}/`(GET/PATCH) · `{id}/confirm|cancel|hold|logs/` · `availability/`(+calendar/). أخطاء جديدة: `no_availability` (409) · `invalid_reservation_transition` (400) · `cancellation_reason_required` (400).
- **قرار موثّق:** `ReservationRoomAssignment` **مؤجّل إلى Phase 7** (تعيين غرفة فعلية جزء من check-in، ولا واجهة له في Phase 6؛ صحة المخزون مضمونة على مستوى نوع الغرفة).

### ما نُفّذ (Frontend)
- **عنصر «الحجوزات»** في sidebar الفندق، وصفحة **`/hotel/reservations`** بتبويبات: نظرة عامة / التوفر / الحجوزات.
- **نظرة عامة**: بطاقات ملخّص + قوائم الوصول/المغادرة القادمة (عرض فقط — **بلا أزرار check-in/out**). **التوفر**: مدقّق مدفوع من الباكند (تواريخ/ضيوف/نوع → بطاقات توفر لكل نوع). **الحجوزات**: قائمة مفلترة/مرقّمة + نافذة إنشاء/تعديل (أسطر غرف ديناميكية + snapshot ضيف + held/confirmed) + نافذة تفاصيل (الأسطر/سجل الحالة/تأكيد/إلغاء/تعديل) + نافذة إلغاء (سبب إلزامي).
- نظام التصميم المركزي + أيقونات lucide، ترجمات **ar/en/tr** كاملة مع RTL/LTR، حالات موحّدة، responsive حقيقي، لا نصوص مكتوبة مباشرة، لا توكن في localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/reservations/{__init__,apps,models,availability,services,serializers,views,urls,tests}.py` + migration.
- **جديدة (Frontend):** `app/hotel/reservations/page.tsx` · `components/hotel/reservations/{OverviewTab,AvailabilityTab,ReservationsTab,index}.tsx` · `lib/api/reservations.ts` · والوثيقة `docs/RESERVATIONS_AND_AVAILABILITY_STRATEGY.md`.
- **معدّلة (Backend):** `apps/rbac/registry.py` (+confirm/assign_room + قسم availability) · `apps/common/exceptions.py` (3 أخطاء) · `config/settings/base.py` (+app) · `config/urls.py` (+urls) · اختبارات regression في hotels/rooms (السماح بجدول reservations).
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `lib/api/{types,errors}.ts` · `lib/format.ts` · قواميس ar/en/tr · `styles/globals.css` · التوثيق (README, DEVELOPMENT_RULES §8c, docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **198/198 OK** (140 سابقة + 58 لـ reservations) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/reservations` مبني) |
| فحص حيّ End-to-End (Django+Next، SQLite) | ✅ توفر 3/3 → حجز مؤكد 2×STD + مؤقت 1×DLX · **overbooking → 409** · **back-to-back → 201** · **overlap → 409** · held بلا expiry → 400 · overview صحيح · لقطات overview/availability/list/AR/موبايل/نافذة الإنشاء Premium وRTL سليم |

### ملاحظات وقرارات
- تحديث اختبارَي regression في Phase 4/5 للسماح بجدول `reservations` (مشروع في Phase 6)، مع بقاء منع guests/payments/invoices/folios/expenses.
- انتهاء الحجز المؤقت يُحسب lazily وقت القراءة — لا حاجة لـ Celery لصحة الحساب (يمكن إضافة مهمة تنظيف لاحقًا).
- قفل أنواع الغرف بترتيب ثابت (pk) لتقليل deadlocks عند التزامن.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا check-in/check-out · لا `occupied` · لا Guest profile/وثائق · لا payments/folio/invoices/expenses · لا مطعم/تنظيف-صيانة workflows · لا ورديات/إغلاق يومي/تقارير · لا موقع عام/حجز عام · لا واتساب/خرائط فعلية.** **لم تبدأ Phase 7.**

### تحديث Phase 6.1 — Minimal Room Assignment Support (2026-07-07)
- **الأساس:** تأكّد رسميًا أن Phase 4 وPhase 5 مدموجتان في `main` (commits `ce8f6e9`/`a683393`، ووجود `apps/hotels`+`apps/rooms` وصفحتَي `/hotel/settings`+`/hotel/rooms`، وPROGRESS_LOG يذكرهما «مكتملة ✅») وأن فحوصات `main` ناجحة (backend 140/140، frontend lint/tsc/build) — ثم بدأ التنفيذ.
- **تعيين غرفة محددة (اختياري) على مستوى السطر بدل نموذج منفصل:** حقل `room` اختياري (FK PROTECT) على `ReservationRoomLine`. عند تعيينه: نفس الفندق ونفس `room_type`، غرفة active وحالتها ليست maintenance/out_of_service/archived، و`quantity = 1`. التعيين **لا يعني** دخول الضيف (check-in يبقى Phase 7).
- **محرك التوفر (6.1):** المخزون المستهلك = (غرف مُعيَّنة محددة distinct ضمن المخزون) + (كمية غير مُعيَّنة)؛ يدعم conflict الغرفة المُعيَّنة + كمية النوع غير المُعيَّنة + المزيج. منع overlap لنفس الغرفة (`409 room_assignment_conflict`)، والسماح بـ back-to-back لنفس الغرفة، وتجاهل cancelled/expired/held المنتهي. قفل أنواع الغرف **والغرف المحددة** بترتيب pk ثابت داخل transaction.
- **الصلاحية:** استخدام `reservations.assign_room` — تعيين غرفة عند الإنشاء/التعديل يتطلبها على الباكند (بخلافها `403`).
- **الواجهة:** مُحدِّد غرفة اختياري لكل سطر بعد اختيار نوع الغرفة (افتراضي «أي غرفة»)، وعرض رقم الغرفة المُعيَّنة في التفاصيل. **لا timeline/Gantt** (متسق مع منع Phase 6 للتقويم المتقدم). ترجمات ar/en/tr مضافة بتطابق مفاتيح.
- **الاختبارات/الفحوصات:** backend **214/214** (198 + 16 لتعيين الغرف)، migration `0002` نظيفة؛ frontend lint/tsc/build خضراء؛ فحص حيّ: تعيين→201، same-room overlap→409، back-to-back→201، نوع خاطئ→400.
- **بلا:** check-in/out، Guest module كامل، payments/folio/invoices. **لم تبدأ Phase 7.**

### الاعتماد
- **معتمدة ومقبولة فنيًا من المالك بتاريخ 2026-07-07** عبر مراجعة PR #5 (Phase 6 + 6.1). الحالة: **مكتملة ✅**. **لم يُغيَّر وضع Phase 7** — يبدأ برسالته الرسمية فقط.

#### ملاحظات الاعتماد (من المالك)
1. التأكد أن Phase 4 موجودة ومكتملة في `origin/main`.
2. التأكد أن Phase 5 موجودة ومكتملة في `origin/main`.
3. التأكد من وجود: `backend/apps/hotels` · `backend/apps/rooms` · `frontend/src/app/hotel/settings` · `frontend/src/app/hotel/rooms`.
4. قبول بناء `apps/reservations`.
5. قبول Model `Reservation`.
6. قبول Model `ReservationRoomLine`.
7. قبول Model `ReservationStatusLog`.
8. قبول `AvailabilityService` كمصدر مركزي لحساب التوفر.
9. قبول قاعدة التداخل نصف المفتوحة `[check_in, check_out)`.
10. قبول السماح بحجوزات back-to-back.
11. قبول منع overbooking من الباكند.
12. قبول الحالات: draft / held / confirmed / cancelled / expired / no_show حسب التنفيذ (نُفِّذت held/confirmed/cancelled/expired؛ لم يُنفَّذ draft/no_show عمدًا — مؤجّلة لـ Phase 7 حسب التوثيق).
13. قبول أن confirmed يحجز التوفر.
14. قبول أن held يحجز التوفر فقط إذا لم ينتهِ.
15. قبول أن cancelled/expired لا تحجز التوفر.
16. قبول دعم unassigned room type availability.
17. قبول دعم assigned room availability بعد Phase 6.1.
18. قبول إضافة `room` اختياري إلى `ReservationRoomLine`.
19. قبول منع same-room overlap.
20. قبول السماح بـ back-to-back لنفس الغرفة.
21. قبول أن اختيار غرفة محددة يتطلب `reservations.assign_room`.
22. قبول منع تعيين غرفة من فندق آخر.
23. قبول منع تعيين غرفة من نوع خاطئ.
24. قبول منع تعيين غرفة maintenance/out_of_service/archived.
25. قبول عزل tenant.
26. قبول حماية endpoints بالصلاحيات.
27. قبول read-only للفندق المعلّق ومنع الكتابة.
28. قبول صفحة `/hotel/reservations`.
29. قبول الترجمة ar/en/tr.
30. قبول responsive وRTL/LTR.
31. قبول عدم بناء check-in/check-out.
32. قبول عدم بناء Guest module كامل.
33. قبول عدم بناء payments/folio/invoices.
34. قبول عدم بناء public booking.
35. قبول عدم بدء Phase 7.
36. قبول نتائج backend tests: 214/214.
37. قبول نتائج frontend lint/typecheck/build.

#### ملاحظة حول `main` المحلي (قرار موثّق)
- ظهر أن **الفرع المحلي `main`** يحتوي تاريخًا مختلفًا وغير مطابق لـ `origin/main`. **`origin/main` هو المصدر الصحيح للحقيقة.** ممنوع دفع الفرع المحلي المختلف إلى `origin/main`، وممنوع reset مدمّر دون موافقة صريحة. أي عمل قادم يبدأ من branch نظيف مبني على `origin/main` (fetch/checkout آمن).

#### ملاحظة مستقبلية
- قبل الإنتاج النهائي: فحص أوسع على PostgreSQL وبيانات أكبر للتأكد من التزامن الحقيقي، الأداء، pagination، الفلاتر، محرك التوفر، ومنع overbooking تحت ضغط أعلى. لا يمنع اعتماد Phase 6 الآن.

---

## Phase 7 — Guests + Check-in + Check-out
- الحالة: **مكتملة ✅** (معتمدة ومقبولة فنيًا من المالك)
- التاريخ: بدأت 2026-07-07 · اكتملت (تنفيذ) 2026-07-07 · **اعتُمدت 2026-07-07**
- الهدف: سجل النزلاء + دورة الاستقبال التشغيلية (check-in لحجز مؤكد داخل غرفة، المقيمون الحاليون، وصول/مغادرة اليوم، check-out تشغيلي). **بلا أي مال.**
- الأساس: بُنيت من **`origin/main`** (c690801، يحوي Phase 4/5/6+6.1) بعد التحقق منه — لم يُستخدم الفرع المحلي المختلف.
- **ملاحظة الاعتماد:** «تم اعتماد Phase 7 كمرحلة استقبال تشغيلية: سجل النزلاء، الإقامة الفعلية، check-in، current residents، arrivals today، departures today، وcheck-out تشغيلي. لا تشمل هذه المرحلة payments أو folio أو invoices أو أي تسوية مالية، ولا public booking.»

### ما نُفّذ (Backend)
- **تطبيقان مستقلان فوق المراحل السابقة:** `apps/guests` (سجل النزلاء) و`apps/stays` (طبقة الإقامة + خدمات check-in/out) — لم يُوضع check-in داخل `apps/reservations`.
- **`Guest`** مربوط بالفندق: الاسم(مطلوب)/الهاتف/البريد/الجنسية/نوع+رقم الوثيقة/تاريخ الميلاد/الجنس/العنوان/ملاحظات/is_active — **رقم الوثيقة فريد لكل فندق+نوع** (فارغ لا يتعارض). **لا مرفقات وثائق** (مؤجّلة).
- **`Stay`** (إقامة فعلية): reservation/reservation_line (nullable)، room(PROTECT)، primary_guest(PROTECT)، status، تواريخ مخطّطة/فعلية، checked_in/out_by، ملاحظات — **قيد partial-unique: إقامة in_house واحدة كحدّ أقصى لكل غرفة** (منع الإشغال المزدوج على مستوى DB).
- **`StayGuest`** (primary/companion): فريد (stay,guest) + **primary واحد لكل إقامة**. **`StayStatusLog`** سجلّ حالة الإقامة.
- **الإشغال مشتق** من إقامة `in_house` — **لا** حالة `occupied` يدوية في `room.status` (يبقى للحالات اليدوية فقط).
- **`CheckInService`** مركزي داخل transaction بقفل الغرفة: الحجز **confirmed** فقط؛ الغرفة **available** فقط (dirty/cleaning/maintenance/out_of_service/archived → `409 room_not_ready`)؛ غير مشغولة (`409 room_occupied`)؛ لا تكرار (`409 already_checked_in`)؛ لا تعارض مع حجز آخر يثبّت الغرفة (`409 room_assignment_conflict`)؛ النزيل/المرافقون من نفس الفندق. قرار موثّق: **لا تقييد تاريخ** (early/late مسموح، بلا رسوم)؛ سطر بكمية>1 يُدخَل غرفة-بغرفة.
- **`CheckOutService`** مركزي: فقط لإقامة `in_house`؛ يختم الوقت/المستخدم؛ يحوّل الغرفة إلى **dirty** (قرار موثّق)؛ **بلا مال/فوليو/فاتورة**.
- **العروض التشغيلية:** المقيمون الحاليون (`in_house`)، وصول اليوم (حجوزات confirmed لليوم غير مكتملة الدخول)، مغادرة اليوم (`in_house` بتاريخ خروج مخطّط = اليوم).
- **الصلاحيات:** `guests.view/create/update/delete` و`stays.view/check_in/check_out/update` — مفروضة على الباكند لكل endpoint؛ الفندق المعلّق للقراءة فقط؛ حذف نزيل مرتبط بإقامة → **تعطيل** بدل حذف.
- **APIs تحت `/api/v1/hotel/`**: `guests/`(+`{id}/`) · `stays/`(+`current/`,`arrivals-today/`,`departures-today/`) · `stays/check-in/` · `stays/{id}/`(GET/PATCH ملاحظات) · `stays/{id}/check-out/` · `stays/{id}/logs/`. أخطاء جديدة: `invalid_check_in`(400) · `invalid_check_out`(400) · `room_occupied`(409) · `room_not_ready`(409) · `already_checked_in`(409).

### ما نُفّذ (Frontend)
- عنصرا **«الاستقبال»** و**«النزلاء»** في sidebar الفندق.
- **`/hotel/guests`**: قائمة نزلاء مع بحث/pagination + إنشاء/تعديل + حذف-أو-تعطيل.
- **`/hotel/front-desk`**: تبويبات **وصول اليوم** (زر check-in → نافذة تستخدم الغرفة المثبّتة أو تطلب اختيارها + اختيار/إنشاء سريع لضيف + مرافقون + ملاحظات) · **المقيمون الحاليون** (بطاقات إشغال + تفاصيل + check-out) · **مغادرة اليوم** (check-out). نافذة الخروج تنبّه أن أي فوترة في مرحلة لاحقة. **بلا أزرار تلمح إلى مال.**
- نظام التصميم المركزي + أيقونات lucide، ترجمات **ar/en/tr** كاملة (namespaces `guests` + `frontDesk`) مع RTL/LTR، حالات موحّدة، responsive حقيقي، لا نصوص مباشرة، لا توكن في localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/guests/{__init__,apps,models,serializers,views,urls,tests}.py` + migration · `apps/stays/{__init__,apps,models,services,serializers,views,urls,tests}.py` + migration.
- **جديدة (Frontend):** `app/hotel/guests/page.tsx` · `app/hotel/front-desk/page.tsx` · `components/hotel/guests/GuestsPanel.tsx` · `components/hotel/frontdesk/FrontDeskPanel.tsx` · `lib/api/{guests,stays}.ts` · والوثيقة `docs/GUESTS_CHECKIN_CHECKOUT_STRATEGY.md`.
- **معدّلة (Backend):** `apps/rbac/registry.py` (+guests.update/delete +قسم stays) · `apps/common/exceptions.py` (5 أخطاء) · `config/settings/base.py` (+appين) · `config/urls.py` (+urls) · تحديث اختبارات regression في hotels/rooms/reservations (السماح بجدولَي guests/stays).
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `lib/api/{types,errors}.ts` · `lib/format.ts` · قواميس ar/en/tr · `styles/globals.css` · التوثيق (README, DEVELOPMENT_RULES §8d, docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **264/264 OK** (214 سابقة + 50 لـ guests/stays) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسارا `/hotel/guests` و`/hotel/front-desk` مبنيان) |
| فحص حيّ End-to-End (Django+Next، SQLite) | ✅ وصول اليوم · check-in (غرفة مثبّتة 101) → in_house · **الغرفة تبقى available (إشغال مشتق)** · المقيمون=1 · check-out → checked_out + **الغرفة dirty** · check-out ثانٍ → **400** · لقطات front-desk (وصول/نافذة دخول/مقيمون)/guests/AR/موبايل Premium وRTL سليم |

### ملاحظات وقرارات
- تعيين غرفة الإدخال يُمنع لغير `available` (بما فيها dirty/cleaning) — قرار موثّق (يمكن إضافة override بصلاحية لاحقًا).
- check-in غير مقيَّد بالتاريخ (early/late مسموح) — قرار موثّق.
- الغرفة تصبح `dirty` بعد الخروج — قرار موثّق.
- تحديث اختبارات regression لمراحل 4/5/6 لإزالة `guests` من المحظور (أصبح مشروعًا في Phase 7)، مع بقاء منع payments/invoices/folios/expenses.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا مال إطلاقًا (payments/expenses/folio/invoices/taxes) · لا تسوية عند الخروج · لا مطعم/كافتيريا · لا housekeeping/maintenance workflows كاملة · لا lost&found · لا ورديات/إغلاق يومي · لا موقع/حجز عام · لا واتساب/خرائط فعلية · لا تقارير متقدمة · لا مرفقات وثائق النزلاء.** **لم تبدأ Phase 8.**

### الاعتماد
- **معتمدة ومقبولة فنيًا من المالك بتاريخ 2026-07-07** عبر مراجعة PR #6. الحالة: **مكتملة ✅**. **لم يُغيَّر وضع Phase 8** — يبدأ برسالته الرسمية فقط.

#### ملاحظات الاعتماد (من المالك)
1. إنشاء `apps/guests`.
2. إنشاء `apps/stays`.
3. قبول Model `Guest`.
4. قبول Model `Stay`.
5. قبول Model `StayGuest`.
6. قبول Model `StayStatusLog`.
7. قبول `CheckInService` كخدمة مركزية.
8. قبول `CheckOutService` كخدمة مركزية.
9. قبول أن الإشغال مشتق من `Stay` وليس من `room.status`.
10. قبول عدم إضافة `occupied` كحالة يدوية للغرفة.
11. قبول منع check-in لغرفة مشغولة.
12. قبول منع check-in لغرفة maintenance/out_of_service/archived.
13. قبول منع check-in لغرف dirty/cleaning في هذه المرحلة.
14. قبول استخدام الغرفة المثبتة على سطر الحجز أو اختيار غرفة عند check-in.
15. قبول منع duplicate check-in.
16. قبول إنشاء Stay وStayGuest primary عند check-in.
17. قبول current residents من `Stay.status = in_house`.
18. قبول arrivals today من الحجوزات المؤكدة غير المدخلة.
19. قبول departures today من الإقامات in_house ذات خروج مخطط اليوم.
20. قبول check-out كتشغيل فقط بدون مال.
21. قبول تحويل الغرفة إلى dirty بعد check-out.
22. قبول أن checkout لا ينشئ folio أو invoice أو payment.
23. قبول صلاحيات: `guests.view/create/update/delete` و`stays.view/check_in/check_out/update`.
24. قبول tenant isolation.
25. قبول read-only للفندق المعلّق ومنع الكتابة.
26. قبول صفحات: `/hotel/guests` و`/hotel/front-desk`.
27. قبول الترجمة ar/en/tr.
28. قبول RTL/LTR والـ responsive.
29. قبول عدم بناء payments/folio/invoices.
30. قبول عدم بناء public booking.
31. قبول عدم بدء Phase 8.
32. قبول نتائج backend tests: 264/264.
33. قبول نتائج frontend lint/typecheck/build.

#### ملاحظة مستقبلية غير مانعة (سياسة الخروج المبكر)
- يجب لاحقًا توثيق ومراجعة سياسة **الخروج المبكر**: هل يبقى الحجز حاجزًا للغرفة حتى تاريخ الخروج المخطط، أم يُحرَّر التوفر بعد check-out الفعلي، وكيف يؤثر ذلك على الحسابات المالية لاحقًا. تُرحَّل إلى Phase 8 أو مرحلة تحسين تشغيل الحجوزات. **لا تمنع اعتماد Phase 7 الآن.**

#### ملاحظة Git
- `origin/main` هو مصدر الحقيقة الوحيد. ممنوع استخدام الفرع المحلي `main` المختلف أو دفعه إلى origin، وممنوع reset مدمّر دون موافقة صريحة.

---

## Phase 8 — Payments + Expenses + Folio + Invoices
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-07 · اكتملت (تنفيذ) 2026-07-07 · تاريخ الاعتماد: 2026-07-07
- الهدف: طبقة المال الداخلية للفندق — **Folio** لكل حجز/إقامة يجمّع **charges** (بضريبة لكل بند)، **payments** كإيصالات، **invoice** تُصدَر من الفوليو كلقطة ثابتة غير قابلة للتعديل، و**expenses** كسندات صرف مستقلة. المال **Decimal فقط**؛ **لا حذف نهائي** للسجلات المنشورة (void بسبب)؛ **الأرصدة محسوبة** من السجلات المنشورة؛ **لا يُغلق فوليو برصيد ≠ 0**.
- الأساس: بُنيت من **`origin/main`** (752ea76، يحوي Phase 4/5/6+6.1/7) بعد التحقق منه — لم يُستخدم الفرع المحلي المختلف.
- **طبقة داخلية فقط:** لا payment gateway فعلي (Stripe/PayPal/دفع أونلاين)، لا bank reconciliation، لا e-invoicing حكومي، لا ledger محاسبي متقدم، لا payroll، لا daily close/shifts.

### ما نُفّذ (Backend)
- **تطبيق واحد `apps/finance`** فوق المراحل السابقة، مع **وحدة خدمات واحدة** (`services.py`) هي المسار الوحيد الذي يكتب المال — الـ views لا تعدّل حقول المال مباشرة.
- **النماذج:** `FinancialNumberSequence` (عدّاد لكل فندق+نوع، فريد hotel+kind) · `Folio` (روابط reservation/stay/guest اختيارية SET_NULL، `folio_number` فريد لكل فندق، status open/closed/voided، عملة، void triple) · `FolioCharge` (folio PROTECT، النوع room/service/tax/adjustment/discount/other، quantity/unit/amount/tax_rate/tax_amount/total، status posted/voided) · `Payment` (إيصال، folio PROTECT، `receipt_number` فريد لكل فندق، method cash/card/bank_transfer/electronic/other) · `Invoice` + `InvoiceLine` (folio PROTECT، draft/issued/voided، `invoice_number` فريد لكل فندق بين غير الفارغ، لقطة بنود+إجماليات+balance_at_issue مجمّدة عند الإصدار) · `Expense` (سند صرف مستقل، `expense_number` فريد لكل فندق، تصنيفات operations/maintenance/supplies/marketing/salary/utilities/other).
- **قواعد المال (مفروضة كودًا):** `MONEY_KW(max_digits=12, decimal_places=2)` + `money()` يقرّب لخانتين ROUND_HALF_UP — **لا float**. **لا hard delete** للسجلات المنشورة → **void** (status + `void_reason` + `voided_at`/`voided_by`؛ سبب فارغ مرفوض). الفوليو يحمل charges/payments/invoices بـ `on_delete=PROTECT`.
- **الرصيد محسوب دائمًا** (لا عمود مخزّن): `folio_balance = Σ posted charges − Σ posted payments`. **لا يُغلق فوليو برصيد ≠ 0.00** (`409 folio_not_balanced`)؛ الإضافة/الدفع فقط على فوليو `open` (`409 folio_closed`).
- **الضريبة** نسبة مئوية لكل بند: `amount=qty×unit`، `tax=amount×rate/100`، `total=amount+tax`؛ البنود غير الائتمانية موجبة (`422 invalid_amount`)؛ لا بند بإجمالي صفر.
- **لقطة الفاتورة (immutability):** الفاتورة تُنشأ **draft** (بلا رقم/بنود) ثم **issue**: نسخ كل charge منشور إلى `InvoiceLine`، تجميد subtotal/tax_total/total + `balance_at_issue`، تخصيص `invoice_number`. بعد الإصدار **لا يتغيّر شيء** بنشاط الفوليو اللاحق — التصحيح بـ void + إعادة إصدار.
- **الترقيم** `next_number(hotel, kind)` بقفل الصف (`select_for_update`) → `FOL/RCP/INV/EXP/CHG{n:05d}`، **لكل فندق** وبلا فجوات؛ رقم الفاتورة يُصرف عند الإصدار فقط (لا فجوات من المسودات).
- **سياسة الخروج المبكر (قرار موثّق):** يدوية لا تلقائية — لا auto-refund/auto-void؛ التخفيض عبر void charge أو adjustment/discount ثم تسوية وإغلاق؛ لا غرامة تلقائية (تُدخل كـ charge عادي).
- **الصلاحيات:** `finance.view/create/update/close/void/charge_create/charge_void/payment_create/payment_void/invoice_create/invoice_issue/invoice_void` و`expenses.view/create/update/void` — مفروضة على الباكند لكل endpoint؛ **الفندق المعلّق للقراءة فقط** (كل كتابة → `403 hotel_suspended`)؛ عزل مستأجرين كامل؛ **فوليو مفتوح واحد لكل إقامة** (`409 open_folio_exists_for_stay`).
- **APIs تحت `/api/v1/hotel/finance/`**: `overview/` · `folios/`(+`{id}/`,`close/`,`void/`,`charges/`,`payments/`,`invoices/`) · `charges/{id}/void/` · `payments/`(+`{id}/void/`,`{id}/receipt/`) · `invoices/`(+`{id}/`,`issue/`,`void/`,`print/`) · `expenses/`(+`{id}/`,`void/`,`voucher/`). أخطاء جديدة: `folio_closed`(409) · `folio_not_balanced`(409) · `void_reason_required`(422) · `invalid_finance_operation`(409) · `invalid_amount`(422). endpoints الطباعة (receipt/print/voucher) تُرجع payload صديق للطباعة بلا أي خدمة خارجية أو PDF على الخادم.

### ما نُفّذ (Frontend)
- عنصر **«المالية»** في sidebar الفندق ومسار **`/hotel/finance`** بتبويبات: **نظرة عامة** (بطاقات: حسابات مفتوحة/الرصيد المستحق/دفعات اليوم/مصروفات اليوم/الصافي اليوم/فواتير صادرة) · **الحسابات** (قائمة+إنشاء+نافذة تفاصيل بالـ charges/payments والرصيد الحيّ وإضافة رسم/تسجيل دفعة/إنشاء فاتورة/إغلاق/إبطال + إيصال قابل للطباعة) · **الدفعات** (إبطال + إيصال) · **الفواتير** (إصدار/إبطال/طباعة) · **المصروفات** (إنشاء/إبطال + سند قابل للطباعة).
- الطباعة عبر `window.print()` على مستند طباعة فقط (`@media print` في `globals.css`) — بلا خادم. تنسيق المال عبر `Intl.NumberFormat` (عملة). نظام التصميم المركزي + أيقونات lucide، ترجمات **ar/en/tr** كاملة (namespace `finance`) مع RTL/LTR، حالات موحّدة، responsive حقيقي، لا نصوص مباشرة، لا توكن في localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/finance/{__init__,apps,models,services,serializers,views,urls,tests}.py` + migration.
- **جديدة (Frontend):** `app/hotel/finance/page.tsx` · `components/hotel/finance/{FinancePanel,OverviewTab,FoliosTab,PaymentsTab,InvoicesTab,ExpensesTab,shared}.tsx` · `lib/api/finance.ts` · والوثيقة `docs/FINANCE_FOLIO_PAYMENTS_INVOICES_STRATEGY.md`.
- **معدّلة (Backend):** `apps/rbac/registry.py` (+قسم `finance` بـ12 رمزًا +توسيع `expenses`) · `apps/common/exceptions.py` (5 أخطاء) · `config/settings/base.py` (+app) · `config/urls.py` (+urls) · تحديث اختبارات regression في hotels/rooms/reservations/stays إلى `test_no_out_of_scope_models` (تمنع restaurant_orders/stock_items/daily_closes/shifts؛ stays تُبقي public_bookings).
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `lib/api/{types,errors}.ts` · `lib/format.ts` (+formatMoney +tone helpers) · قواميس ar/en/tr · `styles/globals.css` (بطاقات رصيد + مستند طباعة) · التوثيق (README, DEVELOPMENT_RULES §8e, docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **302/302 OK** (264 سابقة + 38 لـ finance) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/finance` مبني) |
| فحص حيّ End-to-End (Django+Next، SQLite) | ✅ فوليو FOL00001 → رسم 2×100+15% = رصيد 230 → دفعة 130 = رصيد 100 → **إغلاق محظور 409** → دفعة 100 → مُغلق · فوليو جديد → رسم → إنشاء+إصدار فاتورة INV00001 (إجمالي 55، سطر لقطة واحد) · مصروف EXP00001 · overview: مفتوحة 1/مستحق 55/دفعات اليوم 230/مصروفات اليوم 75/صافي 155/فواتير صادرة 1 · لقطات overview/folios/invoice-print/expenses/AR/موبايل Premium وRTL سليم |

### ملاحظات وقرارات
- **المال Decimal فقط** و**void بدل الحذف** و**الرصيد محسوب** — قرارات معمارية مفروضة كودًا.
- **الفوليو لا يُغلق برصيد ≠ 0**؛ **الفاتورة المُصدَرة لقطة ثابتة** (تصحيح بإبطال+إعادة إصدار) — قرارات موثّقة.
- **سياسة الخروج المبكر يدوية** (لا استرداد تلقائي) — استجابةً لملاحظة Phase 7 المستقبلية؛ موثّقة في §9 من وثيقة الاستراتيجية.
- **card/electronic مجرّد وسم** على إيصال داخلي — لا معالجة فعلية.
- تحديث اختبارات regression لمراحل 4/5/6/7 لأن جداول المال (folios/charges/payments/invoices/expenses) أصبحت مشروعة في Phase 8؛ تبقى تمنع أنطقة لاحقة (restaurant/stock/daily_close/shifts).

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا payment gateway فعلي · لا Stripe/PayPal · لا دفع أونلاين · لا bank reconciliation · لا e-invoicing حكومي · لا ledger محاسبي متقدم · لا payroll · لا daily close · لا shifts · لا مطعم/POS · لا مخزون · لا housekeeping/maintenance workflows · لا public booking payments · لا تقارير مالية متقدمة · لا تحويل عملات (FX) · لا خطط تقسيط · لا proration تلقائي للخروج المبكر.** **لم تبدأ Phase 9.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-07** بعد Final Acceptance Review لـ PR #7 (فحوصات backend 302/302 + frontend lint/typecheck/build ناجحة + تحقق حيّ End-to-End).
- ملاحظة الاعتماد: «تم اعتماد Phase 8 بعد Patch 8.1، والتي حصرت المواءمة ضمن النطاق الحالي فقط: الحجوزات، النزلاء، الاستقبال، المالية، الفوليو، الدفعات، الفواتير، المصروفات، الطباعة، وتحسين الكروت المركزية. تم اعتماد نوعي حجز فقط: instant/future. لا يوجد quick/full booking، ولا public booking، ولا payment gateway، ولا Phase 9.»
- محتوى PR #7 المعتمد: `a0198f2` (Phase 8) + `bd3f075` (Patch 8.1). ملفات graphify (`.graphifyignore`, `graphify-out/`) خارج الرقعة ولا تدخل في أي commit للدمج أو الاعتماد.

#### ملاحظة Git
- `origin/main` هو مصدر الحقيقة الوحيد. ممنوع استخدام الفرع المحلي `main` المختلف أو دفعه إلى origin، وممنوع reset مدمّر دون موافقة صريحة.

---

## Phase 8.1 — Current Scope Real Hotel Data & UX Patch
- الحالة: **معتمدة ✅** (ضمن الاعتماد النهائي لـ Phase 8 — commit `bd3f075` داخل PR #7)
- التاريخ: 2026-07-08
- الطبيعة: **مقارنة محدودة بنطاق ما بُني حتى Phase 8 فقط** (حجوزات، نزلاء، front desk، مالية، طباعة) مع احتياجات الفندق الحقيقي والمشروع القديم كمصدر متطلبات فقط — **ليست Phase 9 وليست إعادة بناء ولا نسخًا من المشروع القديم**.

### ما نُفّذ (Backend)
- **نوعان فقط للحجز** على `Reservation.booking_kind`: `instant` (النزيل موجود الآن — الدخول يُفرض اليوم؛ يُرفض instant بتاريخ دخول مستقبلي) و`future` (لتاريخ لاحق). عند غياب الحقل يشتقّه الباكند من تاريخ الدخول — **لا quick/full booking ولا basic/advanced mode**.
- **حقول تشغيلية جديدة** على الحجز (migration `reservations.0003`): `expected_arrival_time` · `booking_channel_name` · `expected_payment_method` (معلومة فقط — ليست دفعة) · `no_show_reason` · ولقطة النزيل: `primary_guest_nationality` · `primary_guest_document_type` · `primary_guest_document_number`. حقل `notes` يُستخدم كملاحظات داخلية؛ `cancellation_reason` يبقى إلزاميًا عند الإلغاء.
- **الفاتورة**: حقلا لقطة آمنان `customer_email` و`customer_document_number` (migration `finance.0002`) يُملآن من نزيل الفوليو عند الإصدار؛ **مرجع الحجز قراءة علاقة آمنة** (`folio.reservation.reservation_number`) عبر الـ serializers — لا لقطة له لأن رقم الحجز لا يتغيّر؛ **تواريخ الإقامة وأرقام الغرف لم تُخزَّن عمدًا** (ليست لقطة بسيطة/آمنة — مرحلة لاحقة إن لزم).

### ما نُفّذ (Frontend)
- **نموذج حجز واحد** منظَّم في **خمسة أقسام** (`SectionCard`/`StepSummaryCard`): نوع وتواريخ (+عدد ليالٍ محسوب +وقت وصول متوقع) → بيانات النزيل (اسم/هاتف/بريد/جنسية/نوع ورقم وثيقة) → الغرف والتوفر (رسائل تعارض لكل سطر — القرار للباكند) → المصدر والملاحظات (مصدر/قناة/طلبات خاصة/ملاحظات داخلية/طريقة دفع متوقعة) → مراجعة وحفظ (ملخص + زر واضح). نافذة التفاصيل تعرض النوع والحقول الجديدة.
- **`/hotel/front-desk`**: صف **5 بطاقات workflow** مركزية (`WorkflowCard`): وصول اليوم · النزلاء الحاليون · مغادرة اليوم · تسجيل دخول · تسجيل خروج — كلٌّ بأيقونة وعنوان وعدد حيّ ووصف وإجراء. صفوف الوصول/المغادرة عبر `ActionCard`. **نافذة الخروج** تعرض اسم النزيل ورقم الغرفة وتاريخ الدخول الفعلي وتاريخ الخروج المتوقع + تنبيه واضح أن التسوية المالية في قسم المالية + زر تأكيد — **بلا أي دفع داخل الخروج**.
- **الطباعة** عبر مكوّن مركزي `PrintDocumentLayout`: فاتورة (ترويسة الفندق، بيانات العميل + بريد/وثيقة، فوليو + مرجع حجز، بنود، subtotal/tax/total/balance_at_issue، ملاحظات) · إيصال قبض (دافع، مبلغ+عملة، طريقة، مرجع، مستلم، توقيع) · سند صرف (مورّد، تصنيف، وصف، منشئ، توقيع).
- **الدفع المختلط**: **لا نموذج تقسيم دفعة** — تعدد الدفعات على نفس الفوليو هو الآلية؛ نموذج الدفع يعرض تلميحًا («للدفع بأكثر من طريقة سجّل أكثر من دفعة.») وزر **«حفظ وإضافة دفعة أخرى»**.
- **بطاقات مركزية جديدة** في `components/ui`: `WorkflowCard` · `ActionCard` · `SectionCard` · `StatusSummaryCard` · `DocumentPreviewCard` · `PrintDocumentLayout` · `StepSummaryCard` — design tokens فقط، أيقونات lucide، ترجمات **ar/en/tr** كاملة، RTL/LTR، responsive. رصيد الفوليو عبر `StatusSummaryCard`.

### الملفات المضافة/المعدّلة
- **جديدة:** مكوّنات الـ UI السبعة أعلاه · migrations `reservations.0003` و`finance.0002` · `docs/REAL_HOTEL_CURRENT_SCOPE_ALIGNMENT.md`.
- **معدّلة (Backend):** `apps/reservations/{models,serializers}.py` · `apps/finance/{models,services,serializers}.py`.
- **معدّلة (Frontend):** `components/ui/index.ts` · `components/hotel/reservations/ReservationsTab.tsx` · `components/hotel/frontdesk/FrontDeskPanel.tsx` · `components/hotel/finance/{FoliosTab,PaymentsTab,InvoicesTab,ExpensesTab}.tsx` · `lib/api/{types,reservations}.ts` · قواميس ar/en/tr · `styles/globals.css` · وثائق الاستراتيجية الثلاث (حجوزات/نزلاء/مالية).

### ما لم يُنفَّذ (خارج النطاق، عمدًا)
- **لا** موقع عام · **لا** حجز عام · **لا** مطعم/POS · **لا** housekeeping · **لا** maintenance · **لا** lost & found · **لا** shifts · **لا** daily close · **لا** تقارير متقدمة · **لا** إشعارات · **لا** WhatsApp · **لا** خرائط · **لا** عمولة منصة · **لا** توسيع اشتراكات · **لا** بوابة دفع/استرداد. **لم تبدأ Phase 9.** لم يُنسخ أي كود/تنسيق من المشروع القديم — استُخدم كمصدر متطلبات فقط.

### الاعتماد
- **معتمدة ضمن الاعتماد النهائي لـ Phase 8** (قرار المالك بتاريخ 2026-07-07 بعد Final Acceptance Review). جزء من PR #7 بالكومِت `bd3f075`.

---

## Phase 9 — Restaurant / Café / Room Service Orders
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-08 · اكتملت (تنفيذ) 2026-07-08 · تاريخ الاعتماد: 2026-07-08
- الهدف: أساس طلبات الخدمات الداخلية — **كتالوج** (تصنيفات + أصناف بأسعار Decimal وضريبة لكل صنف) و**طلبات** مرتبطة بإقامة/غرفة تمرّ بدورة `submitted → preparing → ready → delivered` ثم **تُرحَّل مرة واحدة فقط إلى فوليو النزيل كرسم واحد** عبر خدمات المال في Phase 8. **بلا POS، بلا مخزون، بلا طاولات، بلا دفع مباشر، بلا بوابة دفع، بلا طلب عام.**
- الأساس: بُنيت من **`origin/main`** (120e455، بعد دمج Phase 8 + 8.1 عبر PR #7).

### ما نُفّذ (Backend)
- **تطبيق مستقل `apps/services`** (لا داخل finance/stays/rooms) مع **وحدة خدمات واحدة** (`services.py`) هي مسار الكتابة الوحيد — الـ views لا تعدّل الطلبات مباشرة.
- **النماذج:** `ServiceCategory` (فريدة الرمز داخل الفندق؛ لا حذف مع وجود أصناف → `409 resource_in_use`) · `ServiceItem` (تصنيف من نفس الفندق، نوع restaurant/cafe/room_service/other، سعر Decimal ≥ 0، ضريبة %، متاح/نشط؛ الصنف المستخدم في طلب لا يُحذف — يُعطَّل) · `ServiceOrder` (`order_number` فريد لكل فندق ORD00001، مصدر، stay/room/folio اختيارية بفحص المستأجر، حالة، ملاحظات، وختم الترحيل `posted_charge` OneToOne→FolioCharge + `posted_at/posted_by`) · `ServiceOrderItem` (**لقطة** اسم/سعر/ضريبة + مجاميع محسوبة بنفس تقريب `money()`) · `ServiceOrderStatusLog` (سجل حالة خفيف — ليس Audit عامًا) · `ServiceNumberSequence` (عدّاد مستقل بقفل صف — لا خلط مع الترقيم المالي).
- **سير الحالات:** أمامي فقط مع سماح بالقفز (submitted→delivered لطلب الكاونتر)؛ العناصر تُعدَّل في **draft فقط**؛ delivered/cancelled/posted مجمّدة (`409 order_not_editable`)؛ الإلغاء بمساره الخاص **وبسبب إلزامي**؛ لا DELETE للطلبات إطلاقًا؛ كل تغيير يُسجَّل.
- **الترحيل إلى الفوليو (المخرج المالي الوحيد):** يتطلب `service_orders.post_to_folio` + حالة **delivered** + عدم ترحيل سابق (**قفل صف** يمنع الترحيل المزدوج المتزامن → `409 order_already_posted`) + إجمالي > 0؛ حلّ الفوليو: فوليو الطلب المفتوح → الفوليو المفتوح للإقامة → **إنشاء فوليو عبر `finance.create_folio`** (بالحجز والنزيل الرئيسي)؛ بلا إقامة وبلا فوليو → `409 order_not_postable`؛ يُنشأ **رسم واحد** عبر `finance.add_charge` بـ `type=service` و`source=service_order` ووصف `Service order ORD00001` — مع تمرير **مجموع ضريبة الطلب الدقيق صراحةً** (توسعة موثّقة صغيرة لـ`add_charge` بمعامل `tax_amount` اختياري) بحيث تساوي مبالغ الرسم مبالغ الطلب للسنت حتى مع اختلاف نسب الضريبة بين الأسطر؛ الطلب المرحّل لا يُلغى — التصحيح **void مالي من قسم المالية فقط** (لا un-post).
- **الصلاحيات:** `services.view/create/update/delete` + `service_orders.view/create/update/cancel/status_update/post_to_folio` (أُضيفت للسجل مع توثيق `restaurant.*` القديمة كـ vestigial)؛ المدير يملك الكل، وStaff بمنح صريح؛ **الفندق المعلّق قراءة فقط** (كل كتابة → `403 hotel_suspended`)؛ عزل مستأجرين كامل (بحث مقيّد بالفندق 404 + `400 cross_tenant_reference`).
- **أخطاء جديدة:** `order_already_posted`(409) · `order_not_postable`(409) · `order_not_editable`(409) · `order_items_required`(422) · `invalid_order_status_transition`(400) · `service_item_unavailable`(422).
- **APIs تحت `/api/v1/hotel/services/`**: `overview/` · `categories/`(+`{id}/`) · `items/`(+`{id}/`، بفلاتر بحث/تصنيف/نوع/توفر/ترتيب) · `orders/`(+`{id}/`,`status/`,`cancel/`,`post-to-folio/`,`ticket/`، بفلاتر حالة/مصدر/إقامة/غرفة/تاريخ/مرحّل) — كلها paginated.

### ما نُفّذ (Frontend)
- عنصر **«الخدمات»** في sidebar الفندق ومسار **`/hotel/services`** بأربعة تبويبات: **نظرة عامة** (بطاقات workflow: طلبات اليوم/في المطبخ/جاهزة/سُلّمت/مُسلّمة غير مرحّلة/مرحّل اليوم/أصناف نشطة) · **الكتالوج** (تصنيفات + أصناف: إنشاء/تعديل/تفعيل/تعطيل/حذف محكوم، فلترة وبحث) · **الطلبات** (إنشاء بطلب لإقامة حالية أو زبون مباشر + محرر أسطر؛ تفاصيل بمجاميع الباكند وسجل الحالات؛ أزرار حالة واضحة؛ إلغاء بسبب؛ ترحيل للفوليو بتأكيد ومقيّد بالصلاحية؛ **تذكرة طباعة** عبر `PrintDocumentLayout`) · **لوحة التحضير** (4 أعمدة حالة بأزرار صريحة — لا سحب/إفلات؛ الباكند يتحقق من كل انتقال).
- **لا حساب مالي في الواجهة**: نموذج الإنشاء لا يعرض مجاميع محلية («تُحسب المجاميع من النظام بعد الحفظ») والمجاميع كلها من ردّ الباكند. مكوّنات 8.1 المركزية (WorkflowCard/StatusSummaryCard/ConfirmDialog/…) + tokens فقط (أُضيف قسم `board-grid` مركزي صغير في globals.css) + lucide + ترجمات **ar/en/tr كاملة** (namespace `services`، تكافؤ 960=960=960) + RTL/LTR + حالات موحّدة + responsive. لا localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/services/{__init__,apps,models,services,serializers,views,urls,tests}.py` + migration `services.0001` · **جديدة (Frontend):** `app/hotel/services/page.tsx` · `components/hotel/services/{ServicesPanel,OverviewTab,CatalogTab,OrdersTab,BoardTab}.tsx` · `lib/api/services.ts` · والوثيقة `docs/SERVICE_ORDERS_RESTAURANT_CAFE_STRATEGY.md`.
- **معدّلة (Backend):** `apps/common/exceptions.py` (+6) · `apps/rbac/registry.py` (+قسمي services/service_orders) · `apps/finance/services.py` (توسعة `add_charge` بـ`tax_amount` اختياري — موثّقة) · `config/settings/base.py` · `config/urls.py`.
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `lib/api/{types,errors}.ts` · `lib/format.ts` (+formatDateTime +serviceOrderStatusTone) · قواميس ar/en/tr · `styles/globals.css` (قسم board) · التوثيق (README، DEVELOPMENT_RULES §8f، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **346/346 OK** (302 سابقة + 44 لـ services) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/services` مبني) |
| فحص حيّ End-to-End (Django، SQLite) | ✅ تصنيف RS + صنفان (25+10% و8+0%) → طلب ORD00001 بمجاميع 58/5/63 → submitted→preparing→ready→delivered → تذكرة (عنصران، 63.00) → **ترحيل**: فوليو FOL00003 أُنشئ تلقائيًا للإقامة + رسم CHG00003 → **رصيد الفوليو 63.00 بالضبط** → ترحيل ثانٍ **409 order_already_posted** → overview: طلبات اليوم 1/مُسلّمة 1/غير مرحّلة 0/مرحّل اليوم 63.00/أصناف نشطة 2 |

### ملاحظات وقرارات
- **رسم واحد لكل طلب** مع تمرير ضريبة الطلب الدقيقة صراحةً (بدل rate-only) — يضمن تطابق الرسم مع الطلب للسنت مع أسطر مختلطة الضرائب؛ `tax_rate` المخزّن على الرسم نسبة فعلية معلوماتية. التوسعة في finance متوافقة رجعيًا (بلا معامل، السلوك السابق حرفيًا).
- إلغاء delivered **غير المرحّل** مسموح (بسبب)؛ المرحّل لا يُلغى نهائيًا — void مالي فقط.
- طلب بإجمالي صفري (أصناف مجانية فقط) لا يُرحَّل (`order_not_postable: zero_total`) — لا رسم صفري في المال.
- التنفيذ الموزّع بالوكلاء غير متاح (حدّ أسبوعي حتى 2026-07-09 مساءً) — نُفِّذت المرحلة مباشرة بنفس التغطية.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا POS كامل · لا مخزون/مشتريات/موردون · لا إدارة/حجز طاولات · لا Kitchen Display متقدم/طابعات مطبخ · لا باركود · لا كاشير مستقل · لا دفع مباشر مستقل/بوابة دفع · لا طلب عام/QR · لا Delivery/WhatsApp orders · لا تقارير مبيعات متقدمة · لا Daily close/Shifts/Payroll.** **لم تبدأ Phase 10.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-08** بعد Final Acceptance Review لـ PR #8 (commit `43ce68d` على `origin/main@120e455`، mergeable_state: clean، backend 346/346، frontend lint/typecheck/build ناجحة، `/hotel/services` مبني).
- ملاحظة الاعتماد: «تم اعتماد Phase 9 بعد Final Acceptance Review. المرحلة أضافت أساس طلبات الخدمات الداخلية: ServiceCategory, ServiceItem, ServiceOrder, ServiceOrderItem, ServiceOrderStatusLog، مع ترحيل آمن إلى Folio عبر FolioCharge، ومنع الترحيل المكرر، وتطبيق tenant isolation والصلاحيات وhotel suspended. لا POS كامل، لا inventory/stock، لا payment gateway، لا public ordering، ولا Phase 10.»
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 10 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 10 — Housekeeping + Maintenance + Lost & Found
- الحالة: **مكتملة ✅** (معتمدة من المالك ومدمجة في main)
- التاريخ: بدأت 2026-07-08 · اكتملت (تنفيذ) 2026-07-08 · تاريخ الاعتماد والدمج: 2026-07-08
- الهدف: أساس العمليات التشغيلية اليومية المرتبطة بالغرف — **مهام التنظيف** (HK00001) و**طلبات الصيانة** (MT00001، قد تحجب الغرفة maintenance/out_of_service) و**سجل المفقودات** (LF00001) — بتكامل آمن مع حالة الغرفة (Phase 5) وتدفق المغادرة (Phase 7). **بلا Shifts، بلا Daily Close، بلا تقارير متقدمة، بلا Inventory، بلا Purchasing.**
- الأساس: بُنيت من **`origin/main`** (98a3d53، بعد دمج Phase 9 عبر PR #8).

### ما نُفّذ (Backend)
- **تطبيق مستقل `apps/operations`** (لا داخل rooms/stays/finance) مع **وحدة خدمات واحدة** (`services.py`) هي مسار الكتابة الوحيد — الـ views لا تغيّر أي حالة مباشرة، و**كل تغيير لحالة الغرفة يمر حصرًا عبر `rooms.services.change_room_status`** (مسار Phase 5 المضبوط: تحقق + تسجيل في RoomStatusLog).
- **النماذج:** `HousekeepingTask` (غرفة مطلوبة عند الإنشاء — FK بـ SET_NULL لبقاء التاريخ؛ إقامة اختيارية؛ نوع checkout/daily/deep/inspection/other؛ أولوية low/normal/high/urgent؛ طوابع started/completed/cancelled؛ سبب إلزامي للإلغاء) · `MaintenanceRequest` (غرفة/إقامة اختياريتان؛ عنوان/وصف/تصنيف electrical…other؛ `affects_room_availability` + `room_block_status` maintenance/out_of_service؛ resolution_notes؛ طوابع كاملة) · `LostFoundItem` (عنوان/وصف/تصنيف electronics…other؛ مكان العثور/التخزين؛ روابط اختيارية غرفة/إقامة/نزيل؛ بيانات المستلم؛ **بلا صور/ملفات/باركود**) · **3 سجلات حالة خفيفة** (HK/MT/LF StatusLog — تشغيلية، ليست Audit عامًا) · `OperationsNumberSequence` (عدّاد لكل فندق ولكل نوع بقفل صف — HK/MT/LF منفصلة عن الترقيم المالي والخدمي).
- **سير الحالات:** HK: `pending→assigned→in_progress→completed` (+إلغاء بسبب)؛ MT: `open→assigned→in_progress→resolved→closed` (+إلغاء بسبب من الحالات المفتوحة فقط)؛ LF: `found→stored→claimed→returned→closed` أو `found/stored→disposed→closed`. نقاط `status/` العامة للتقدم الأمامي غير النهائي فقط؛ الإجراءات النهائية (`complete/`,`resolve/`,`close/`,`cancel/`,`claim/`,`return/`,`dispose/`) نقاط مخصصة بمدخلاتها الإلزامية؛ السجلات المكتملة/المغلقة/الملغاة مجمّدة (`409 operation_not_editable`)؛ **لا DELETE إطلاقًا**؛ كل تغيير حالة يُسجَّل.
- **تكامل حالة الغرفة:** بدء مهمة تنظيف → الغرفة `cleaning` (فقط إن كانت dirty/available)؛ إكمالها **مع إتاحة صريحة** → `available` فقط إذا لم تكن الغرفة maintenance/out_of_service/archived **ولا يوجد طلب صيانة حاجب مفتوح** (وإلا `409 room_blocked_by_maintenance`)؛ إكمال بلا إتاحة أو إلغاء مهمة جارية → `cleaning` تعود `dirty`؛ طلب صيانة حاجب → الغرفة `maintenance`/`out_of_service` عند الإنشاء/التعديل؛ **الإغلاق لا يحرر الغرفة تلقائيًا أبدًا** — `close/` (بعد resolved فقط) يطلب `room_next_status` صريحًا keep/dirty/available، و`available` تُرفض مع وجود طلب حاجب آخر؛ إلغاء طلب حاجب يعيد الغرفة `dirty` (لا available) إن لم يبقَ حاجب آخر؛ **لا `occupied` في Room.status** — الإشغال يبقى مشتقًا من Stay.
- **تكامل المغادرة (Phase 7):** check-out ما يزال يجعل الغرفة dirty كما هو؛ **أُضيف auto-create موثّق ومُختبَر**: مهمة `checkout_cleaning` واحدة لكل إقامة (idempotent بفحص exists على الإقامة+النوع) داخل نفس المعاملة (لا اعتماديات خارجية يمكن أن تفشل).
- **الصلاحيات:** اكتمل قسما `housekeeping` (view/create/update/cancel/status_update/assign) و`maintenance` (+close) وأُضيف `lost_found` (view/create/update/status_update/close) في السجل المركزي؛ المدير يملك الكل؛ Staff بمنح صريح ولا يفتح قسمٌ قسمًا آخر؛ مالك المنصة بلا عضوية ممنوع؛ عزل كامل (استعلامات مقيدة بالفندق + 404 للمراجع الأجنبية + `400 cross_tenant_reference` للمُسند غير العضو)؛ **الفندق المعلّق قراءة فقط** (`403 hotel_suspended` لكل كتابة)؛ `overview/` تكفيها أي صلاحية عرض من الثلاث (فئة any-of مخصصة).
- **أخطاء جديدة:** `invalid_operation_status_transition`(400) · `operation_not_editable`(409) · `room_blocked_by_maintenance`(409) · `claimant_required`(422) · `disposal_reason_required`(400).
- **APIs تحت `/api/v1/hotel/operations/`**: `overview/` (غرف متسخة/تنظيف منتظر وجارٍ/صيانة مفتوحة/غرف محجوبة/مفقودات مفتوحة/مهام عاجلة) · `housekeeping/`(+`{id}/`,`status/`,`assign/`,`complete/`,`cancel/`) · `maintenance/`(+`{id}/`,`status/`,`assign/`,`resolve/`,`close/`,`cancel/`) · `lost-found/`(+`{id}/`,`status/`,`claim/`,`return/`,`dispose/`,`close/`) — كلها paginated بفلاتر بحث/حالة/نوع/تصنيف/أولوية/غرفة/مُسند/تاريخ/ترتيب حسب القسم.

### ما نُفّذ (Frontend)
- عنصر **«التشغيل»** في sidebar الفندق ومسار **`/hotel/operations`** بخمسة تبويبات: **نظرة عامة** (7 بطاقات WorkflowCard) · **التنظيف** (فلاتر حالة/أولوية/غرفة + إنشاء + إجراءات: أسند إليّ/بدء/إكمال بخيار «إتاحة الغرفة أو إبقاؤها متسخة»/إلغاء بسبب) · **الصيانة** (إنشاء بعنوان/وصف/تصنيف/أولوية/غرفة اختيارية/يؤثر على التوفر + اختيار maintenance أو out_of_service؛ إجراءات: أسند إليّ/بدء/حل/إغلاق بخيار حالة الغرفة التالية keep/dirty/available/إلغاء بسبب) · **المفقودات** (تسجيل/حفظ/مطالبة/تسليم/إتلاف بسبب/إغلاق — بلا صور/ملفات) · **لوحة حالة الغرف** (6 مجموعات حسب الحالة: available/dirty/cleaning/maintenance/out_of_service/archived؛ رقم الغرفة/الطابق/النوع/آخر مهمة/آخر طلب مفتوح؛ **الإشغال شارة «إقامة حالية» مشتقة من Stay — ليس حالة غرفة**؛ أزرار سريعة: مهمة تنظيف/صيانة/جعلها متسخة/جعلها متاحة حيث يكون آمنًا).
- الإسناد في الواجهة «أسند إليّ» عمليًا (لا endpoint لسرد أعضاء الفندق بعد — إدارة الموظفين مرحلة لاحقة؛ الباكند يدعم الإسناد لأي عضو). مكونات مركزية فقط + tokens (أُضيف modifier مركزي واحد `board-grid--wide`) + ترجمات **ar/en/tr كاملة** (namespace `operations`، تكافؤ **1154=1154=1154**) + RTL/LTR + حالات موحّدة + responsive. لا localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/operations/{__init__,apps,models,services,serializers,views,urls,tests}.py` + migration `operations.0001` · **جديدة (Frontend):** `app/hotel/operations/page.tsx` · `components/hotel/operations/{OperationsPanel,OverviewTab,HousekeepingTab,MaintenanceTab,LostFoundTab,RoomBoardTab}.tsx` · `lib/api/operations.ts` · والوثيقة `docs/HOUSEKEEPING_MAINTENANCE_LOST_FOUND_STRATEGY.md`.
- **معدّلة (Backend):** `apps/common/exceptions.py` (+5) · `apps/rbac/registry.py` (إكمال housekeeping/maintenance + إضافة lost_found) · `apps/stays/services.py` (auto-create مهمة تنظيف المغادرة) · `config/settings/base.py` · `config/urls.py`.
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `lib/api/{types,errors}.ts` · `lib/format.ts` (+4 tone helpers) · قواميس ar/en/tr · `styles/globals.css` (modifier واحد) · التوثيق (README، DEVELOPMENT_RULES §8g، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **417/417 OK** (346 سابقة + 71 لـ operations) — انحدار صفر للمراحل 2→9 |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/operations` مبني) |
| فحص حيّ End-to-End (عبر BFF) | ✅ check-out → الغرفة dirty + **HK00001 checkout_cleaning تلقائيًا (مرة واحدة)** → أسند إليّ → بدء (الغرفة cleaning) → إكمال مع إتاحة (الغرفة available، سجل كامل) → إكمال ثانٍ **400** → **MT00001 حاجب** (الغرفة maintenance) → محاولة إتاحة من التنظيف **409 room_blocked_by_maintenance** → حل (الغرفة تبقى maintenance — لا تحرير تلقائي) → إغلاق باختيار dirty (الغرفة dirty) → **LF00001** → حفظ → تسليم بلا مستلم **422** → تسليم باسم → إغلاق → عدّادات overview دقيقة قبل/بعد |

### ملاحظات وقرارات
- الإتاحة قرار صريح دائمًا: التنظيف لا يتجاوز حجب الصيانة حتى لو أعاد أحدهم حالة الغرفة يدويًا (يُفحص أيضًا وجود طلب حاجب مفتوح)، وإغلاق الصيانة يطلب اختيارًا صريحًا لحالة الغرفة التالية — لا رجوع تلقائي غامض.
- auto-create بعد المغادرة نُفِّذ لأنه آمن وبسيط (idempotent، بلا اعتماديات خارجية، داخل معاملة المغادرة عمدًا) — موثّق ومغطّى باختبارين.
- تركيب `overview/` بصلاحيات any-of احتاج فئة مخصصة: تركيب `|` القياسي في DRF كان سينفجر لأن صلاحياتنا ترفع استثناء بدل إرجاع False.
- التنفيذ الموزّع بالوكلاء غير متاح (حدّ أسبوعي حتى 2026-07-09 مساءً) — نُفِّذت المرحلة مباشرة بنفس التغطية.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا Shifts/Staff scheduling/Payroll · لا Daily Close · لا تقارير متقدمة · لا Inventory/Stock · لا Purchasing/Suppliers · لا Laundry inventory · لا إشعارات (WhatsApp/Email) · لا تطبيق جوال · لا QR tasks · لا IoT · لا طلبات نزلاء عامة · لا صور/ملفات/باركود للمفقودات · لا بوابة دفع · لا POS.** **لم تبدأ Phase 11.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-08** ومدمجة إلى main عبر **PR #9** بدمج squash — كومِت الدمج `07492c1` (اعتماد مبدئي ثم فحص ما قبل الدمج: **لا أحرف Unicode مخفية/ثنائية اتجاه ضارة** — تنبيه GitHub سببه النص العربي/RTL العادي في 7 ملفات (القواميس والوثائق) وتأكد ذلك بمسح برمجي لكل ملفات الـ PR؛ ومراجعة Copilot بلا أي ملاحظة blocking).
- تحقق ما بعد الدمج: origin/main يحتوي Phase 10 كاملة؛ diff بين main وفرع phase-10 **فارغ**؛ backend `check`/`makemigrations --check`/**417/417 tests** ✅ على main المدموج؛ frontend lint/tsc/build ✅ (`/hotel/operations` مبني).
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 11 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 11 — Staff + Permissions Management UI
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-08 · اكتملت (تنفيذ) 2026-07-08 · تاريخ الاعتماد: 2026-07-08
- الهدف: واجهة إدارة موظفي الفندق وصلاحياتهم **المرنة** فوق أساس Phase 2 كما هو — **لا أدوار ثابتة تتحكم بالوصول أبدًا**: العضوية + منح الصلاحيات هي مصدر الحقيقة الوحيد، و`job_title` مسمى وصفي فقط. **بلا Shifts، بلا Payroll، بلا حضور وانصراف، بلا Scheduling، بلا HR، بلا دعوات بريد.**
- الأساس: بُنيت من **`origin/main`** (1f7d97a، بعد دمج Phase 10 عبر PR #9 = 07492c1).

### ما نُفّذ (Backend)
- **لا نظام RBAC جديد ولا نماذج جديدة**: `apps/staff` تطبيق API رقيق فوق `tenancy.HotelMembership` + `rbac.HotelPermissionGrant` وخدمات rbac القائمة (`grant/revoke/get_hotel_permissions/has_hotel_permission`). أُضيفت **حقول وصفية فقط** إلى HotelMembership (هجرة tenancy.0002): `job_title` · `staff_code` · `notes` · `deactivated_at` · `deactivation_reason` · `created_by` · `updated_by` (البقية موجودة أصلًا: created_at كتاريخ انضمام، phone على User، is_active).
- **السجل المركزي**: اكتمل قسم `staff` بـ view/create/update/deactivate/permissions_view/permissions_update (+`manage` القديمة موثّقة vestigial) — 81 كودًا في 18 قسمًا.
- **دورة الحياة**: إنشاء مستخدم جديد (بريد فريد عالميًا → `409 email_already_registered`، كلمة مرور عبر `validate_password` مجزأة ولا تعود في أي استجابة، معاملة ترجع كاملة عند الفشل) · **ربط مستخدم موجود** بالبريد (تكرار عضوية → `409 membership_already_exists`؛ **مالك المنصة يُرفض دائمًا** → `platform_owner_not_manageable` — قرار موثّق) · تعديل حقول **وصفية فقط** (الاسم/الهاتف/المسمى/الرمز/الملاحظات؛ البريد هوية ثابتة؛ نوع العضوية والتفعيل والمنح خارج PATCH بنيويًا) · **تعطيل/إعادة تفعيل بدل الحذف** (لا DELETE؛ المعطّل يفقد الوصول فورًا عبر `membership_inactive` القائمة ويحتفظ بسجله ومنحه) · **حماية آخر مدير نشط** → `409 last_manager_protected` · إعادة تعيين كلمة مرور محلية (بلا أي بريد — التسليم خارج النظام، موثّق).
- **إدارة المنح**: `PUT permissions/` استبدال كامل transaction-safe (حذف الزائد + get_or_create بلا تكرار)؛ كود غير معروف → `unknown_permission` بلا أي تغيير جزئي؛ **حارس التصعيد**: غير المدير لا يمنح — لنفسه أو لغيره — صلاحية لا يملكها (`403 permission_escalation_blocked`) والإزالة حرة؛ **منح المدير غير قابلة للتعديل** (`409 manager_permissions_not_editable`) لأنه يملك الكل بحكم النوع.
- **سياق الواجهة**: `GET my-permissions/` (عضوية فقط — عن الذات): `{is_manager, permissions[]}` — يغذي السايدبار والحارس. `GET permission-registry/` يعيد السجل مجمّعًا حسب الأقسام (المصفوفة تُبنى منه — لا hardcode في الواجهة).
- **أخطاء جديدة (6)**: `email_already_registered` · `membership_already_exists` · `last_manager_protected` · `platform_owner_not_manageable` · `permission_escalation_blocked` · `manager_permissions_not_editable`.
- **APIs تحت `/api/v1/hotel/staff/`**: `overview/` · `` (list/create بفلاتر بحث/نشاط/نوع/has_permission/ترتيب) · `{id}/` (GET/PATCH) · `{id}/deactivate|reactivate|permissions|reset-password/` · `link-existing-user/` · `permission-registry/` · `my-permissions/` — عزل كامل والفندق المعلّق قراءة فقط (`hotel_suspended` لكل كتابة).

### ما نُفّذ (Frontend)
- **سايدبار يحترم الصلاحيات** (النقطة المحورية): `HotelAccessProvider` يحمّل `my-permissions` مرة واحدة، وخريطة مركزية واحدة `hotelRouteAccess.ts` تربط كل مسار بأكواده (any-of): stays/reservations/guests/finance|expenses/services|service_orders/housekeeping|maintenance|lost_found/staff/rooms/settings — الرابط لا يظهر إلا لحامل الصلاحية (المدير يرى الكل؛ أثناء التحميل لا شيء بدل وميض روابط ممنوعة)، و`HotelRouteGuard` يعرض «الوصول مرفوض» واضحة عند الدخول اليدوي. **الإخفاء تجميلي**: كل API يمنع بنفسه (مُختبر).
- عنصر **«الموظفون»** ومسار **`/hotel/staff`** بأربعة تبويبات: **نظرة عامة** (6 بطاقات) · **قائمة الموظفين** (بحث/فلترة نشط-معطّل، إنشاء بمودال كامل بكلمة مرور مؤقتة لا تُعرض ثانية، ربط مستخدم موجود، تعديل وصفي، تعطيل بمودال تحذير وسبب اختياري، إعادة تفعيل بتأكيد، إعادة تعيين كلمة مرور — وبعد الإنشاء/الربط يُفتح تبويب الصلاحيات للعضو الجديد مباشرة) · **مصفوفة الصلاحيات** (اختيار موظف؛ بطاقة لكل قسم بمفاتيح لكل عملية + تحديد الكل/مسح للقسم + عداد الممنوح + حفظ/استرجاع لا يُفعَّلان إلا عند تغيير فعلي؛ تحذير أصفر عند تعديل الذات + تحديث سياق السايدبار فورًا بعده؛ رسالة «المدير يملك كل شيء» بدل مصفوفة عبثية؛ ملاحظة للمعطّل) · **مرجع الصلاحيات** (من registry API حصرًا مع تسميات مترجمة لكل قسم وعملية وfallback آمن لأي كود مستقبلي + بيانا «المسمى لا يمنح وصولًا» و«المنح مصدر الحقيقة»).
- مكونات مركزية فقط + tokens (**صفر CSS جديد هذه المرحلة**) + ترجمات **ar/en/tr كاملة** (namespace `staff`، تكافؤ **1294=1294=1294**) + RTL/LTR + حالات موحّدة + responsive. لا localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/staff/{__init__,apps,services,serializers,views,urls,tests}.py` (بلا models.py — عمدًا) + هجرة `tenancy.0002` · **جديدة (Frontend):** `app/hotel/staff/page.tsx` · `components/hotel/staff/{StaffPanel,OverviewTab,StaffListTab,PermissionsMatrixTab,RegistryTab}.tsx` · `components/layout/HotelRouteGuard.tsx` · `lib/session/{HotelAccessContext.tsx,hotelRouteAccess.ts}` · `lib/api/staff.ts` · والوثيقة `docs/STAFF_PERMISSIONS_MANAGEMENT_STRATEGY.md`.
- **معدّلة (Backend):** `apps/tenancy/models.py` (حقول وصفية) · `apps/rbac/registry.py` (قسم staff) · `apps/common/exceptions.py` (+6) · `config/settings/base.py` · `config/urls.py`.
- **معدّلة (Frontend):** `app/hotel/layout.tsx` (Provider + Guard) · `components/layout/Sidebar.tsx` (فلترة بالصلاحيات + رابط الموظفين) · `lib/api/{types,errors}.ts` · قواميس ar/en/tr · التوثيق (README، DEVELOPMENT_RULES §8h، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **464/464 OK** (417 سابقة + 47 لـ staff) — انحدار صفر للمراحل 2→10 |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/staff` مبني) |
| فحص حيّ End-to-End (عبر BFF) | ✅ my-permissions للمدير (is_manager=true، 81 صلاحية) → إنشاء موظفة بصلاحية stays.view فقط (لا password في الرد) → دخولها: my-permissions تعيد صلاحيتها فقط؛ stays 200؛ finance 403؛ staff 403 → المدير يمنحها إدارة الصلاحيات → محاولتها منح نفسها finance.view **403 permission_escalation_blocked** → إزالتها صلاحية من نفسها تنجح → المدير يعطّل نفسه **409 last_manager_protected** → تعديل منح المدير **409 manager_permissions_not_editable** → كود مجهول **400 unknown_permission** → registry (18 قسمًا/81 كودًا) → تعطيل («إجازة») → وصولها **403 membership_inactive** → إعادة تفعيل → تعمل → صفحة `/hotel/staff` 200 |

### ملاحظات وقرارات
- **قوالب الصلاحيات (Presets) أُجّلت عمدًا** (المواصفة سمحت بذلك صراحة): كانت ستعقّد المصفوفة دون قيمة جوهرية؛ أي قالب مستقبلي = ملء أولي لمربعات ثم منح عادية.
- **ترقية/تنزيل نوع العضوية** (staff↔manager) خارج نطاق المرحلة — موثّقة كمؤجلة؛ PATCH وصفي بنيويًا لا يستطيع لمسها.
- ربط مالك المنصة كموظف فندق **مُنع كليًا** (الخيار الأكثر أمانًا الذي رجحته المواصفة) — الفصل التام بين النطاقين.
- الإسناد في تبويبات Operations ما يزال «أسند إليّ»؛ قائمة أعضاء كاملة للإسناد يمكن أن تُبنى لاحقًا فوق `staff.view` (تحسين مؤجل).
- التنفيذ الموزّع بالوكلاء غير متاح (حدّ أسبوعي حتى 2026-07-09 مساءً) — نُفِّذت المرحلة مباشرة بنفس التغطية.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا أدوار ثابتة تتحكم بالوصول · لا Shifts · لا حضور وانصراف/بصمة · لا Payroll/عقود ورواتب · لا Staff scheduling · لا HR كامل · لا دعوات بريد حقيقية · لا WhatsApp للموظفين · لا إشعارات متقدمة · لا Activity audit عام · لا تقارير متقدمة.** **لم تبدأ Phase 12.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-08** بعد Final Acceptance Review لـ PR #10 (commit `9e9681d` على `origin/main@1f7d97a`، mergeable_state: clean، backend 464/464، frontend lint/typecheck/build ناجحة، `/hotel/staff` مبني، والبنود الـ24 المقبولة رسميًا في رسالة الاعتماد).
- ملاحظة الاعتماد: «تم اعتماد Phase 11 بعد Final Acceptance Review. المرحلة أضافت واجهة إدارة الموظفين والصلاحيات المرنة اعتمادًا على HotelMembership و HotelPermissionGrant و permission registry، بدون أدوار ثابتة تتحكم بالوصول. job_title وصفي فقط، والصلاحيات هي مصدر الحقيقة. تم تفعيل staff APIs، permission registry، permissions matrix، my-permissions، HotelAccessProvider، HotelRouteGuard، واحترام السايدبار للصلاحيات. تم اختبار منع التصعيد، حماية آخر manager، منع وصول staff المعطّل، tenant isolation، وhotel suspended. لا Shifts، لا Payroll، لا Attendance، ولا Phase 12.»
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 12 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 12 — Shifts + Handover + Daily Close
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-08 · اكتملت (تنفيذ) 2026-07-08 · تاريخ الاعتماد: 2026-07-08
- الهدف: منظّم العمل اليومي — **ورديات بصندوق نقدي** (SH00001) و**تسليم وردية** (HO00001) و**إغلاق يوم تشغيلي** (DC00001) بقفل تأسيسي آمن — **ليس Attendance ولا Payroll ولا HR ولا نظام محاسبة كامل، ولا مصدر حقيقة مالية جديد** (سجلات Phase 8 تبقى المصدر الوحيد).
- الأساس: بُنيت من **`origin/main`** (2a3de9a، بعد دمج Phase 11 عبر PR #10).

### ما نُفّذ (Backend)
- **تطبيق مستقل `apps/shifts`** (لا داخل finance/staff/operations) بوحدة خدمات واحدة هي مسار الكتابة الوحيد — **لا ينشئ ولا يعدّل أي سجل مالي**؛ الربط يحدث داخل `apps/finance/services` نفسها وهذا التطبيق يقرأ فقط.
- **النماذج:** `Shift` (رقم فريد، business_date، مسؤول، افتتاحي/متوقع/فعلي/فرق، ملاحظات؛ **قيد DB: وردية مفتوحة واحدة لكل مستخدم لكل فندق**؛ أكثر من وردية مفتوحة للفندق مسموح — موثّق؛ حالة `closing` محجوزة غير مستخدمة لأن الإغلاق ذري — موثّق) · `ShiftHandover` (من وردية open/closed إلى عضو نشط؛ 6 خانات ملاحظات: ملخص/مهام معلقة/نقد/نزلاء/صيانة/مفقودات) · `DailyClose` (فريد لكل فندق+تاريخ؛ snapshot_json/totals_json توثيقية؛ حالة `reopened` وصلاحية `reopen` محجوزتان — **reopen غير مبني عمدًا وموثّق**) · **3 سجلات حالة خفيفة** · `ShiftsNumberSequence` (SH/HO/DC بقفل صف، منفصلة عن كل التسلسلات).
- **ربط المال (FK لا snapshot — خيار المواصفة المفضل):** حقل `shift` nullable على Payment وExpense (هجرة finance.0003)؛ عند الإنشاء في خدمات المال، وردية المنشئ المفتوحة تُربط تلقائيًا؛ **غياب الوردية لا يكسر العملية** — تصبح **unassigned movement** معروضة بعدّها ومجموعها في overview/summary/اللقطة (لا تُخفى).
- **حساب الصندوق (خادم فقط):** `expected_cash` = الافتتاحي + مدفوعات نقدية POSTED − مصروفات نقدية POSTED للوردية؛ غير النقدي معلوماتي بالطريقة؛ المبطل مستثنى؛ **فرق العد يتطلب سببًا** (`cash_difference_reason_required`)؛ إغلاق بقفل صف؛ **إلغاء وردية عليها حركات ممنوع** (تُغلق حسب الأصول)؛ المغلقة تاريخ لا يُعدَّل منه إلا `internal_notes`.
- **business_date:** خدمة خلفية (`get_business_date`) بحسب timezone الفندق من HotelSettings عبر zoneinfo، وإلا timezone الخادم (موثّق)؛ تمرير التاريخ يدويًا **للمدير فقط** (وفتح وردية بالنيابة كذلك)؛ حدّ موثّق: مقارنات `paid_at__date` بتوقيت التخزين كتقريب في هذه المرحلة.
- **التسليم:** `draft→submitted→accepted|rejected(بسبب)` + إلغاء (بسبب) من draft/submitted؛ **القبول/الرفض للمستلم أو المدير فقط** (`handover_not_recipient`) بعد بوابة `shifts.accept_handover`؛ المقبول مجمّد؛ `to_user` عضو نشط من نفس الفندق.
- **إغلاق اليوم:** `prepare` ينشئ/يحدّث DRAFT بلقطة حديثة (idempotent، لا يقفل شيئًا)؛ `close` يتحقق — **لا ورديات مفتوحة للتاريخ** (`open_shifts_prevent_close`) و**لا تسليمات submitted غير محسومة** (`pending_handovers_prevent_close`) و**مرة واحدة فقط** (`day_already_closed`) — ثم يخزّن اللقطة النهائية (مدفوعات/مصروفات بعدد وإجمالي ونقدي ومبطل، ترحيلات الخدمات، وصول/مغادرة، الورديات بفروقها، التسليمات المعلقة، غير المرتبط).
- **قفل اليوم المغلق (عبر الخدمات المركزية حصرًا):** `ensure_business_day_open` تُستدعى من `finance.record_payment` و`finance.create_expense` (تاريخ paid_at) و`services.post_order_to_folio` (الترحيل الآن) وكل عمليات shifts/daily-close → `409 business_day_closed`. **حدود موثّقة:** الإبطال المالي يبقى مسموحًا بعد الإغلاق (مسار التصحيح الرسمي لقاعدة Phase 8: void بسبب لا delete)، ورسوم الفوليو/الفواتير خارج قفل هذه المرحلة (فوترة نزيل لا حركة صندوق يومية) — موثّق في الاستراتيجية.
- **الصلاحيات:** قسم `shifts` جديد (view/create/update/close/cancel/handover/accept_handover) و`daily_close` اكتمل (view/prepare/close + reopen محجوزة + run vestigial — موثّق)؛ المدير يملك الكل؛ overview بأي من صلاحيتي العرض (فئة any-of — نمط Phase 10)؛ عزل كامل؛ **المعلّق قراءة فقط** (`hotel_suspended` لكل كتابة).
- **أخطاء جديدة (9):** `shift_already_open` · `shift_not_open` · `cash_difference_reason_required` · `handover_not_recipient` · `rejection_reason_required` · `business_day_closed` · `day_already_closed` · `open_shifts_prevent_close` · `pending_handovers_prevent_close`.
- **APIs تحت `/api/v1/hotel/shifts/`**: `overview/` · `current/` · الورديات (list/create بفلاتر حالة/تاريخ/مسؤول/بحث، detail/PATCH، close/cancel/summary) · التسليمات (list/create/detail/PATCH + submit/accept/reject/cancel) · `daily-close/` (list + prepare + close + detail بالتاريخ) — كلها paginated وبلا أي DELETE.

### ما نُفّذ (Frontend)
- عنصر **«الورديات»** في السايدبار (محكوم بـ `shifts.view|daily_close.view` في خريطة المسارات المركزية) ومسار **`/hotel/shifts`** بخمسة تبويبات: **نظرة عامة** (7 بطاقات: مفتوحة/اليوم/تسليمات معلقة/النقد المتوقع/غير المرتبط/آخر إغلاق/حالة اليوم) · **ورديتي الحالية** (فتح بمودال، ملخص صندوق حي، إغلاق بمودال يعرض المتوقع والفرق لحظيًا ويطلب السبب، تسليم مباشر) · **الورديات** (بحث/فلاتر، إغلاق من القائمة بجلب المتوقع أولًا، إلغاء بسبب، مودال ملخص بالطرق) · **التسليمات** (إنشاء باختيار وردية مفتوحة وعضو من قائمة Staff الحقيقية + 6 خانات ملاحظات؛ submit/accept بتأكيد/reject وcancel بسبب) · **إغلاق اليوم** (تاريخ + ملاحظات، **prepare** يعرض اللقطة كاملة قبل الإغلاق، **close** بـ ConfirmDialog وتحذير صريح، قائمة الأيام المغلقة).
- مكونات مركزية فقط + tokens (**صفر CSS جديد**) + ترجمات **ar/en/tr كاملة** (namespace `shifts`، تكافؤ **1442=1442=1442**) + RTL/LTR + حالات موحّدة + responsive + ConfirmDialogs لكل الإجراءات الحساسة. لا localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/shifts/{__init__,apps,models,services,serializers,views,urls,tests}.py` + هجرتا `shifts.0001` و`finance.0003` · **جديدة (Frontend):** `app/hotel/shifts/page.tsx` · `components/hotel/shifts/{ShiftsPanel,OverviewTab,CurrentShiftTab,ShiftsTab,HandoversTab,DailyCloseTab}.tsx` · `lib/api/shifts.ts` · والوثيقة `docs/SHIFTS_HANDOVER_DAILY_CLOSE_STRATEGY.md`.
- **معدّلة (Backend):** `apps/finance/models.py` (+FK shift على Payment/Expense) · `apps/finance/services.py` (قفل اليوم + auto-attach في record_payment/create_expense) · `apps/services/services.py` (قفل الترحيل) · `apps/common/exceptions.py` (+9) · `apps/rbac/registry.py` (+shifts، إكمال daily_close) · `config/settings/base.py` · `config/urls.py` · **حراس نطاق في 6 اختبارات قديمة** حُدِّثوا (كانوا يؤكدون غياب shifts/daily_closes «لم تُبنَ بعد» — أصبحت مبنية بأمر رسمي؛ صاروا يمنعون payroll/attendance) — مسجّل في buglog.
- **معدّلة (Frontend):** `components/layout/Sidebar.tsx` · `lib/session/hotelRouteAccess.ts` · `lib/api/{types,errors}.ts` · `lib/format.ts` (+2 tone helpers) · قواميس ar/en/tr · التوثيق (README، DEVELOPMENT_RULES §8i، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **519/519 OK** (464 سابقة + 55 لـ shifts) — انحدار صفر للمراحل 2→11 |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/shifts` مبني) |
| فحص حيّ End-to-End (عبر BFF) | ✅ فتح SH00001 بافتتاحي 100 → فتح ثانٍ لنفس المستخدم **409** → دفعة نقدية 50 عبر واجهة المال **التصقت تلقائيًا بالوردية** → المتوقع 150.00 → إغلاق بـ 140 بلا سبب **400** → بسبب: فرق −10.00 مسجّل → HO00001 → submit → إغلاق اليوم **409 open_shifts** ثم **409 pending_handovers** → قبول المستلمة بعد منحها `shifts.accept_handover` من مصفوفة Phase 11 (بوابة الصلاحية قبل حارس المستلم — بالتصميم) → دفعة 5.00 بلا وردية = **unassigned معروضة بصدق** → DC00001 مغلق بلقطة (مدفوعات 55.00 نقدًا، ورديتان بفروقهما، غير المرتبط 5.00) → إغلاق ثانٍ **409** → **القفل**: دفعة/مصروف/فتح وردية على اليوم المغلق كلها **409 business_day_closed** → التفاصيل بالتاريخ + الصفحة 200 |

### ملاحظات وقرارات
- FK بدل snapshot لربط المال (خيار المواصفة المفضل) — لا تكرار للمال كحقيقة ثانية؛ اللقطة توثيق فقط.
- الإبطال المالي بعد إغلاق اليوم **يبقى مسموحًا عمدًا** — هو مسار التصحيح الرسمي (void بسبب، Phase 8)؛ ورسوم الفوليو/الفواتير خارج قفل هذه المرحلة — كلاهما موثّق.
- `closing` و`reopened`/`daily_close.reopen` محجوزة غير مستخدمة (موثّقة) — لا تغيير مخطط عند بناء night-audit/reopen مستقبلًا.
- تحديث حراس النطاق الستة هو التعديل الوحيد على اختبارات سابقة — مسجّل في buglog.
- التنفيذ الموزّع بالوكلاء غير متاح (حدّ أسبوعي حتى 2026-07-09 مساءً) — نُفِّذت المرحلة مباشرة بنفس التغطية.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا Attendance/بصمة · لا Payroll/رواتب وعقود · لا HR · لا Staff scheduling · لا Night Audit متقدم · لا إقفال محاسبي نهائي · لا reopen لليوم المغلق · لا تقارير متقدمة · لا ضريبة متقدمة/دفتر أستاذ · لا Inventory/Purchasing/Suppliers · لا إشعارات/WhatsApp · لا Public booking/بوابة دفع.** **لم تبدأ Phase 13.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-08** بعد Final Acceptance Review لـ PR #11 (commit `ca2530b` على `origin/main@2a3de9a`، mergeable_state: clean، backend 519/519، frontend lint/typecheck/build ناجحة، `/hotel/shifts` مبني، والبنود الـ28 المقبولة رسميًا في رسالة الاعتماد).
- ملاحظة الاعتماد: «تم اعتماد Phase 12 بعد Final Acceptance Review. المرحلة أضافت نظام الورديات وتسليم الوردية وإغلاق اليوم التشغيلي، مع Shift وShiftHandover وDailyClose وسجلات حالة وترقيم SH/HO/DC. تم ربط Payment/Expense بالوردية المفتوحة تلقائيًا عند الإمكان، وحساب expected cash من الباكند، وعرض unassigned movements، وتطبيق daily close lock على العمليات الآمنة: payments، expenses، post-to-folio للخدمات، وعمليات الورديات. بقيت void/corrections مسموحة كمسار تصحيح رسمي حسب التوثيق. لا Attendance، لا Payroll، لا HR، لا advanced reports، لا Inventory، ولا Phase 13.»
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 13 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 13 — Reports + Analytics
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-08 · اكتملت (تنفيذ) 2026-07-08 · تاريخ الاعتماد: 2026-07-08
- الهدف: تقارير تشغيلية وإدارية **للقراءة فقط** فوق كل ما بُني (المراحل 5→12) — **ليست BI ولا محاسبة متقدمة ولا مركز تصدير ولا Dashboards تسويقية**.
- الأساس: بُنيت من **`origin/main`** (05e4d67، بعد دمج Phase 12 عبر PR #11).

### ما نُفّذ (Backend)
- **تطبيق مستقل `apps/reports` بلا أي نموذج جديد** (قرار المواصفة المفضل — `ReportExportLog` الاختياري أُجّل موثقًا): كل رقم يُحسب عند الطلب من سجلات المصدر؛ **GET حصرًا** (POST → 405 — اختبار)؛ لا كتابة تشغيلية أو مالية في أي مسار.
- **نطاق التواريخ:** `date_from/date_to` معًا أو لا شيء (الافتراضي الشهر الحالي بحسب business_date للفندق من خدمة Phase 12 — منطقة الفندق الزمنية وإلا الخادم)؛ from ≤ to؛ **سقف 366 يومًا** (حارس أداء موثّق)؛ النطاق الفارغ أصفار لا 500؛ الواجهة لا تُصدر تاريخًا كمصدر وحيد.
- **التقارير التسعة:** `overview/` (حجوزات مؤكدة/ملغاة/منتهية — لا no-show في النموذج موثّق؛ وصول/مغادرة؛ مقيمون الآن؛ نسبة إشغال؛ حالات غرف؛ مدفوعات/مصروفات/صافي حركة؛ خدمات ومرحّلها؛ تشغيل مفتوح؛ ورديات وأيام مغلقة) · `reservations/` (حالة/مصدر/**instant-future**/نوع غرفة + متوسط ليالٍ + وصول/مغادرة يوميًا + قائمة مرقّمة) · `occupancy/` (**مشتق من فترات الإقامة حصرًا** — الإقامة تغطي D إذا دخلت ≤D وخرجت >D؛ الملغاة لا تُحسب؛ النسبة = ليالٍ مشغولة ÷ (غرف نشطة غير مؤرشفة × أيام)؛ حالات الغرف الآنية بلا «occupied» — اختبار غياب صريح) · `guests/` (جدد/جنسيات/**متكررون ≥ إقامتين**/مقيمون/مغادرون/قائمة) · `finance/` (طرق/تصنيفات/يوميات/فواتير صادرة/فوليوهات؛ **voided مستثنى من المجاميع ومعروض عدًّا** — قاعدة موثقة؛ **net_cashflow_simple لا يُسمى ربحًا أبدًا** — اختبار يمنع الكلمة في الحمولة) · `services/` (حالات/مصادر/مُسلَّم مرحّل وغير مرحّل/إجمالي المرحّل من posted_charge/أعلى 10 أصناف بلا الملغاة) · `operations/` (تنظيف/صيانة/مفقودات بالحالة والتصنيف والأولوية + عاجل + تحت الصيانة الآن) · `shifts/` (حالات، مجاميع متوقع/معدود/فرق، تسليمات، **حركات غير مرتبطة**، أيام مغلقة) · `daily-close/` (قائمة + تفاصيل اليوم من **لقطته المخزنة كتوثيق** بينما الأرقام الحية تُعاد من المصدر — موثّق).
- **المال:** Decimal حصرًا عبر `money()` مُسلسل نصوصًا — لا float في أي مسار (اختبار نوع صريح).
- **CSV بسيط لثلاثة تقارير جدولية** (حجوزات/مدفوعات/ورديات): خلف `reports.export` **AND** صلاحية القسم؛ نفس الفلاتر والعزل؛ **سقف 5000 صف**؛ بلا أعمدة حساسة (اختبار header)؛ النطاق الفارغ ترويسة فقط لا 500.
- **الصلاحيات:** قسم `reports` اكتمل: view (الأساسية) / finance / operations / shifts (يشمل daily-close) / export؛ المدير يملك الكل؛ **الفندق المعلّق يقرأ التقارير والـ CSV بحسب صلاحياته** (قرار موثّق ومختبَر: قراءة صرفة بلا أي مسار كتابة).
- لا استثناءات جديدة (validation القياسي يكفي) ولا هجرات (`makemigrations --check` نظيف).

### ما نُفّذ (Frontend)
- عنصر **«التقارير»** في السايدبار (خلف `reports.view` في خريطة المسارات) ومسار **`/hotel/reports`**: **فلاتر عالمية واحدة أعلى الصفحة** (من/إلى + نطاقات سريعة: اليوم/آخر 7/هذا الشهر/الشهر الماضي + تطبيق/استرجاع) تسري على **8 تبويبات**: نظرة عامة (10 بطاقات + **طباعة عبر PrintModal/PrintDocumentLayout المركزيين**) · الحجوزات · الإشغال (مع تنويه «الإشغال من الإقامات») · النزلاء · **المالية** (تنويه «أرقام تشغيلية وليست تقريرًا محاسبيًا» + زر CSV) · الخدمات · التشغيل · الورديات وإغلاق اليوم (+CSV). تبويبات finance/operations/shifts **تُخفى بلا صلاحيتها** والـ API يرفض بمعزل عن الإخفاء.
- **بلا Charts** (قرار موثّق): لا مكتبة رسوم ولا CSS جديد — بطاقات وجداول مركزية (`useReport/BucketTable/DayTable` مشتركة في shared.tsx بنمط finance/shared). ترجمات **ar/en/tr كاملة** (namespace `reports`، تكافؤ **1576=1576=1576**) + RTL/LTR + حالات موحّدة + responsive. لا localStorage.
- **إصلاح مصاحب ضروري وموثّق:** وكيل BFF `/api/hotel/[...path]` كان يضيف شرطة نهائية لكل مسار فيكسر `export.csv` (404) — بات يتخطاها عندما يحوي المقطع الأخير نقطة؛ بقية المسارات كما هي (اختبار حي قبل/بعد) — مسجّل في buglog.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/reports/{__init__,apps,services,views,urls,tests}.py` (بلا models.py وبلا migrations — عمدًا) · **جديدة (Frontend):** `app/hotel/reports/page.tsx` · `components/hotel/reports/{ReportsPanel,shared,OverviewTab,ReservationsTab,OccupancyTab,GuestsTab,FinanceTab,ServicesTab,OperationsTab,ShiftsTab}.tsx` · `lib/api/reports.ts` · والوثيقة `docs/REPORTS_ANALYTICS_STRATEGY.md`.
- **معدّلة (Backend):** `apps/rbac/registry.py` (إكمال قسم reports) · `config/settings/base.py` · `config/urls.py`.
- **معدّلة (Frontend):** `app/api/hotel/[...path]/route.ts` (إصلاح الشرطة النهائية للمسارات الملفّية) · `components/layout/Sidebar.tsx` · `lib/session/hotelRouteAccess.ts` · `lib/api/types.ts` · قواميس ar/en/tr · التوثيق (README، DEVELOPMENT_RULES §8j، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected (لا نماذج جديدة) |
| `manage.py test` | ✅ **553/553 OK** (519 سابقة + 34 لـ reports) — انحدار صفر للمراحل 2→12 |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/reports` مبني) |
| فحص حيّ End-to-End (عبر BFF فوق بيانات المراحل الحقيقية) | ✅ التقارير التسعة 200 بأرقام مطابقة لسجلات dev: مدفوعات 55.00 نقدًا/صافي 55.00، فرق ورديات −10.00 بسببه، 5.00 غير مرتبطة معروضة، DC00001 بلقطته، إشغال 0 ليالٍ لدخول-خروج بنفس اليوم (متسق رياضيًا) → نطاق مقلوب **400** → موظفة بلا reports.\* **403** → بمنح `reports.view` فقط: overview 200 وfinance/shifts **403** وexport **403** → CSV المدير 200 ببيانات حقيقية (سطر الفرق والسبب) وpayments.csv بلا أعمدة حساسة → overview لا يحوي «profit» → صفحة `/hotel/reports` 200 |

### ملاحظات وقرارات
- **لا نماذج جديدة** (خيار المواصفة المفضل) و**لا Charts** (بطاقات وجداول تكفي) و**CSV لثلاثة تقارير فقط** بسقف صفوف — كلها موثقة مع بدائلها المؤجلة.
- المعلّق يقرأ ويصدّر CSV (قراءة صرفة) — القرار موثّق في الاستراتيجية والاختبارات.
- إصلاح وكيل BFF للمسارات الملفّية كان ضروريًا لمسارات `export.csv` التي نصّت عليها المواصفة حرفيًا — أصغر تعديل ممكن ومسجّل في buglog.
- خطأ اسم حقل أثناء التطوير (`Invoice.total` لا `total_amount`) اكتُشف بالاختبارات وأُصلح — مسجّل في buglog.
- التنفيذ الموزّع بالوكلاء غير متاح (حدّ أسبوعي حتى 2026-07-09 مساءً) — نُفِّذت المرحلة مباشرة بنفس التغطية.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا BI متقدم · لا Data warehouse · لا Pivot/Report designer · لا تقارير مجدولة/بريد/WhatsApp · لا Notifications · لا موقع عام/حجز عام · لا بوابة دفع · لا محاسبة متقدمة/دفتر أستاذ/ضريبة متقدمة · لا تقارير Payroll/Attendance/Inventory/Purchasing · لا تحليلات مالك المنصة المتقدمة.** **لم تبدأ Phase 14.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-08** بعد Final Acceptance Review لـ PR #12 (commit `9762cec` على `origin/main@05e4d67`، mergeable_state: clean، backend 553/553، frontend lint/typecheck/build ناجحة، `/hotel/reports` مبني، والبنود الـ34 المقبولة رسميًا في رسالة الاعتماد).
- ملاحظة الاعتماد: «تم اعتماد Phase 13 بعد Final Acceptance Review. المرحلة أضافت تقارير تشغيلية وإدارية read-only تشمل overview، reservations، occupancy، guests، finance، services، operations، shifts/daily close، مع date filters، CSV exports محدودة وآمنة، وصلاحيات reports.*. الإشغال مشتق من Stay وليس Room.status، وnet_cashflow_simple ليس profit بل صافي حركة تشغيلية. لا BI advanced، لا public booking، لا payment gateway، لا notifications، لا scheduled reports، ولا Phase 14.»
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 14 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 14 — Notifications + Activity Center
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-09 · اكتملت (تنفيذ) 2026-07-09 · تاريخ الاعتماد: 2026-07-09
- الهدف: مركز إشعارات **داخلي** وسجل نشاط تشغيلي مبسط — **ليست WhatsApp ولا Email ولا Push ولا SMS ولا Chat ولا Audit Log قانونيًا**.
- الأساس: بُنيت من **`origin/main`** (3ab3646، بعد دمج Phase 13 عبر PR #12).

### ما نُفّذ (Backend)
- **تطبيق مستقل `apps/notifications`** بنموذجين + عدّاد: `ActivityEvent` (ACT00001 — نوع/تصنيف من 11 فئة/خطورة من 4/عنوان/رسالة/فاعل/مستهدَف/مرجع كائن/رابط/metadata/occurred_at؛ **سجل تشغيلي مبسط للواجهة، ليس Audit قانونيًا ولا بديلًا عن سجلات الحالة القائمة**؛ append-only بلا DELETE) · `Notification` (NTF00001 — لمستلم واحد؛ read/archived بطوابعهما؛ **صندوق خاص**: المستخدم يرى إشعاراته فقط والمدير يرى الاتساع عبر مركز النشاط لا صناديق الآخرين) · `NotificationsNumberSequence` بقفل صف. **NotificationPreference أُجّل عمدًا** (خيار المواصفة المفضل — موثّق).
- **المسار الوحيد للإنشاء**: `record_activity` المركزي — خدمات النطاق تستدعيه بعد نجاح كتابتها (استيراد كسول)؛ لا view ينشئ حدثًا. **أمان المحتوى**: `safe_metadata` تُسقط مفاتيح password/token/secret/authorization/api_key وتُبقي البدائيات فقط؛ `safe_related_url` مسارات داخلية `/…` حصرًا (https/‏//‏/javascript تُفرَّغ) — اختبارات صريحة لكليهما.
- **منطق المستلمين** (`eligible_recipients`): عضويات الفندق النشطة بمستخدمين نشطين؛ **المدير دائمًا + حامل صلاحية عرض مطابقة للفئة** (خريطة CATEGORY_VIEW_CODES: finance→finance/expenses.view، operation→housekeeping/maintenance/lost_found.view، shift→shifts/daily_close.view، reservation/stay→reservations/stays.view، staff→staff.view…)؛ `system/report` للمديرين فقط؛ **الفاعل لا يُشعَر بفعله**؛ المعطّل/فندق آخر/مالك المنصة بلا عضوية: لا شيء أبدًا؛ منع التكرار — كلٌّ باختباره.
- **الأحداث المربوطة (13 نوعًا — المجموعة الإلزامية كاملة):** `reservation.created/cancelled` · `stay.checked_in/checked_out` · `payment.recorded/voided` · `service_order.posted_to_folio` · `housekeeping.task_created/task_completed` · `maintenance.request_created/request_resolved` · `shift.closed` (warning عند فرق صندوق) · `daily_close.closed` · `staff.permissions_updated` (بمستهدَف). **المؤجل موثّق** (confirmed/no_show، room.marked_dirty، lost_found.*، expense/invoice/folio، service created/delivered/cancelled، shift.opened، handover.*، staff created/deactivated/reactivated) — كل إضافة لاحقة سطر استدعاء واحد.
- **الصلاحيات**: `notifications.view/update` + `activity.view/view_all` في السجل. **رؤية النشاط**: المدير أو view_all = كل الفندق؛ view فقط = فئات صلاحياته **+ أحداثه كفاعل أو مستهدَف** (قاعدة موثقة — مُثبتة حيًا: موظفة رأت حدث تحديث صلاحياتها هي).
- **الفندق المعلّق**: القراءة **وقراءة/أرشفة الإشعارات** مسموحة (قرار موثّق: أعلام user-state على صندوق المستخدم، لا كتابة تشغيلية) — مُختبر.
- **APIs تحت `/api/v1/hotel/notifications/`**: `overview/` · `unread-count/` (لشارة الجرس) · القائمة/التفاصيل (صندوق المستخدم فقط بفلاتر unread/archived/category/severity/date) · `mark-read/`,`mark-all-read/`,`archive/` · `activity/`(+detail بفلاتر category/severity/event_type/actor/date) — paginated بلا أي DELETE ولا قناة خارجية.

### ما نُفّذ (Frontend)
- **جرس Topbar** (نُفِّذ — قرار موثّق): شارة عدد غير المقروء لواجهة الفندق تُحمَّل **مرة واحدة** عند فتح القشرة (لا realtime ولا polling — عمدًا)، تختفي كليًا بلا `notifications.view`، والنقر ينقل للصفحة.
- عنصر **«الإشعارات»** في السايدبار (خلف `notifications.view|activity.view`) ومسار **`/hotel/notifications`** بثلاثة تبويبات: **نظرة عامة** (6 بطاقات: غير مقروء/تحذيرات/حرجة/اليوم/مؤرشفة/نشاط اليوم) · **الإشعارات** (فلاتر + أزرار غير المقروء/المؤرشفة + قراءة/الكل/أرشفة/فتح الرابط الداخلي) · **مركز النشاط** (نوع الحدث بتسمية مترجمة وfallback آمن، الفاعل/الوقت/الرابط؛ لا تعديل ولا حذف). **لا تبويب تفضيلات** (مؤجلة).
- مكونات مركزية فقط + **صفر CSS جديد** + ترجمات **ar/en/tr كاملة** (namespace `notifications` شاملًا تسميات 13 نوع حدث و11 فئة و4 خطورات، تكافؤ **1648=1648=1648**) + RTL/LTR + حالات موحّدة + responsive. لا localStorage.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/notifications/{__init__,apps,models,services,serializers,views,urls,tests}.py` + migration `notifications.0001` · **جديدة (Frontend):** `app/hotel/notifications/page.tsx` · `components/hotel/notifications/{NotificationsPanel,OverviewTab,InboxTab,ActivityTab}.tsx` · `components/layout/NotificationBell.tsx` · `lib/api/notifications.ts` · والوثيقة `docs/NOTIFICATIONS_ACTIVITY_CENTER_STRATEGY.md`.
- **معدّلة (Backend):** `apps/rbac/registry.py` (+قسمي notifications/activity) · **خطافات الأحداث** في `apps/{reservations,stays,finance,services,operations,shifts,staff}/services.py` (استدعاء record_activity الكسول بعد الكتابة الناجحة — 13 موضعًا) · `config/settings/base.py` · `config/urls.py`.
- **معدّلة (Frontend):** `components/layout/{Topbar,Sidebar}.tsx` · `lib/session/hotelRouteAccess.ts` · `lib/api/types.ts` · قواميس ar/en/tr · التوثيق (README، DEVELOPMENT_RULES §8k، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **593/593 OK** (553 سابقة + 40 لـ notifications) — انحدار صفر رغم 13 خطافًا في 7 خدمات قائمة |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/hotel/notifications` مبني) |
| فحص حيّ End-to-End (عبر BFF) | ✅ إنشاء مهمة تنظيف ولّد **ACT00001** (info، برابط `/hotel/operations`) → المدير الفاعل **غير مُشعَر** (unread 0) → بعد منح موظفة `housekeeping.view+notifications.*` استلمت **NTF00001** لمهمة جديدة → قراءة ✓ أرشفة ✓ → مركز نشاطها المقيد أظهر فئة operation **+ حدث staff المستهدِف لها** (القاعدة الموثقة) → دفعة على تاريخ أمس المغلق رُفضت **409 business_day_closed** (قفل Phase 12 سليم عبر حدود اليوم) → الصفحة 200 للمدير والموظفة |

### ملاحظات وقرارات
- جرس Topbar **بُني** (كان اختياريًا): الـ Topbar بسيط والتكلفة سطرين — تحميل واحد بلا polling.
- NotificationPreference **مؤجل** (خيار المواصفة المفضل)؛ الافتراضيات المبنية على الصلاحيات كافية.
- عناوين/رسائل الأحداث بيانات سجل (كسجلات الحالة السابقة)؛ الواجهة تترجم التسميات (النوع/الفئة/الخطورة) — متسق مع سوابق المشروع.
- خادم dev قديم منهار احتجز :3000 مجددًا أثناء الـ E2E — قُتل وأعيد نظيفًا (نمط مسجّل في buglog سابقًا).

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا WhatsApp · لا Email · لا SMS · لا Push · لا Chat/Mentions/Threads · لا realtime/WebSocket متقدم · لا جدولة/قوالب خارجية · لا حملات تسويق · لا رسائل نزلاء عامة · لا NotificationPreference · لا Audit Log قانوني/SIEM · لا Public website/booking · لا Payment gateway.** **لم تبدأ Phase 15.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-09** بعد Final Acceptance Review لـ PR #13 (commit `214c9fa` على `origin/main@3ab3646`، mergeable_state: clean، backend 593/593، frontend lint/typecheck/build ناجحة، `/hotel/notifications` مبني، والبنود الـ30 المقبولة رسميًا في رسالة الاعتماد — مع ملاحظة المالك غير المانعة: تقرير التنفيذ ذكر 13 نوع حدث والمراجعة النهائية أثبتت 14 نوعًا مطابقًا للقائمة المطلوبة، فرق لصالح التنفيذ).
- ملاحظة الاعتماد: «تم اعتماد Phase 14 بعد Final Acceptance Review. المرحلة أضافت مركز إشعارات داخلي وسجل نشاط تشغيلي مبسط عبر ActivityEvent وNotification وترقيم ACT/NTF، مع NotificationBell في Topbar، وصفحة /hotel/notifications، ومنطق recipients يحترم الصلاحيات والعضوية النشطة. تم تأمين metadata_json من الأسرار، وحصر related_url بالمسارات الداخلية، ومنع رؤية إشعارات الغير، وحماية activity visibility. تم ربط 14 نوع حدث داخليًا دون كسر التدفقات الأصلية. لا WhatsApp، لا Email، لا SMS، لا Push، لا Chat، لا public messaging، ولا Phase 15.»
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 15 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 15 — Public Website + Public Booking
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-09 · اكتملت (تنفيذ) 2026-07-09 · تاريخ الاعتماد: 2026-07-09
- الهدف: موقع عام يرى فيه الزائر الفنادق **المنشورة** ويحجز **بلا دفع وبلا حساب عميل** — ويصل الحجز إلى كونسول الحجوزات القائم نفسه.
- الأساس: بُنيت من **`origin/main`** (ac3472a، بعد دمج Phase 14 عبر PR #13).

### ما نُفّذ (Backend)
- **قرار إعادة الاستخدام أولًا (موثّق):** حقول العرض العام موجودة أصلًا في `HotelSettings` من Phase 4 (الاسم/الوصف/النجوم/العملة/التواصل/الموقع/أوقات الدخول والخروج/سياسة الإلغاء) و`HotelMedia` (شعار/غلاف/معرض) — **لم تُنسخ**؛ أُضيف فقط ما لم يكن موجودًا: **`HotelSettings` +8** (`public_is_listed` · `public_slug` فريد · `public_booking_requires_confirmation` افتراضي true · `public_min_nights`/`public_max_nights` · `public_terms_text` · `public_sort_order` · `public_featured`) — و`allow_public_booking` (Phase 4) هو مفتاح الحجز. **`RoomType` +5** (`public_is_visible` · `public_name` · `public_description` · `public_base_price` · `public_sort_order` — بfallback للاسم/الوصف/السعر الداخلي). **`Reservation` +4 + مصدر جديد** (`ReservationSource.PUBLIC_WEBSITE` · `public_manage_token_hash` · `public_manage_token_created_at` · `public_cancel_requested_at` · `public_cancel_reason`).
- **تطبيق مستقل `apps/public_site`** تحت **`/api/v1/public/`** — مجهول الهوية بالكامل (`authentication_classes=[]` + `AllowAny`) خلف **Throttling بنطاقين**: `public` (300/دقيقة) للقراءة و`public_booking` (60/ساعة) للكتابة.
- **العرض العام**: قائمة الفنادق المنشورة فقط (ACTIVE + مدرج + slug، ببحث q/city/country وسقف)، تفاصيل الفندق (هوية/سياسات/شروط/معرض/أنواع الغرف المرئية فقط) — **لا يتسرب شيء داخلي أبدًا**: لا موظفون ولا مالية ولا فوليو ولا ملاحظات داخلية ولا أرقام غرف ولا فنادق أخرى (اختبارات صريحة).
- **التوفر عبر المحرك نفسه**: `AvailabilityService.availability_for_type` من Phase 6 — **أعداد فقط** لكل نوع مرئي، مع تحقق تواريخ عام (لا ماضٍ، ≤366 يومًا، حدود min/max nights).
- **الحجز العام عبر `create_reservation` الداخلي نفسه** (Overbooking مستحيل تجاوزه — 409 `no_availability` كالكونسول تمامًا): **`booking_kind=future` دائمًا** (لا check-in تلقائي أبدًا)، الحالة الافتراضية **`held` بحجز 72 ساعة موثّق** (`PUBLIC_HOLD_HOURS`؛ `confirmed` فقط إذا عطّل الفندق التأكيد)، قناة `Funduqii Public`، سقوف 5 غرف/20 ضيفًا/طلبًا، **لا Payment ولا Invoice ولا Folio ولا Stay** (اختبار صريح). خطاف Phase 14 `reservation.created` يعمل تلقائيًا — إشعار الطاقم **بصفر كود جديد**.
- **رمز الإدارة (Manage token)**: `secrets.token_urlsafe(32)` يُعرض للزائر **مرة واحدة فقط** في استجابة الإنشاء؛ يُخزَّن **SHA-256 فقط**؛ المقارنة بـ`hmac.compare_digest`؛ **مرجع خاطئ ورمز خاطئ = 404 واحد لا يُفرَّق** (لا Enumeration oracle).
- **طلب الإلغاء طلبٌ فقط**: يختم `public_cancel_requested_at` + السبب (idempotent — الطلب الأول يثبت) و**لا يلغي ولا يفرّغ ولا يحذف شيئًا أبدًا** — الفندق يقرر عبر سير عمل Phase 6 القائم.
- **العزل**: فندق غير مدرج/معلّق = 404 في كل شيء؛ حجز معطّل = 403؛ نوع غرفة مخفي/من فندق آخر = 404 (اختبارات لكلٍّ).
- Migrations: `hotels.0002` · `rooms.0002` · `reservations.0004`.

### ما نُفّذ (Frontend)
- **BFF عام بلا جلسة**: `app/api/public/[...path]/route.ts` → Django `/api/v1/public/...` (GET/POST فقط، بلا كوكيز ولا توكنات) + `lib/api/public.ts`.
- **الصفحات العامة**: **`/`** صفحة رئيسية عامة (بدل التحويل القديم — مع إبقاء رابطي تسجيل الدخول و«تجربة مجانية») · **`/hotels`** دليل ببحث · **`/hotels/[slug]`** ملف الفندق + فحص التوفر + **نموذج الحجز** (تواريخ → أعداد حية → بيانات الضيف → موافقة على الشروط → مرجع + رمز لمرة واحدة مع تحذير حفظ ونسخ) · **`/booking/manage`** (مرجع + رمز → عرض الحالة + طلب إلغاء).
- **مكونات `components/public/`** (`PublicShell` · `PublicHotelCard` · `PublicBookingPanel`) من عناصر UI المركزية فقط + قسم CSS واحد في `globals.css` بالتوكنات حصرًا.
- **جانب الفندق**: قسم **«الموقع العام»** في صفحة الإعدادات (إدراج/slug/مفتاح الحجز — نُقل إليه من قسم الافتراضيات/تأكيد إلزامي/مميز/حدود الليالي/الشروط) · حقول عامة في مودال نوع الغرفة (ظهور/اسم/وصف/سعر) · تسمية مصدر `public_website` في الحجوزات (**عرضًا فقط — ليست خيارًا في نموذج الإنشاء**) · **بانر تحذيري لطلب الإلغاء** في تفاصيل الحجز (الوقت + السبب) · **hash الرمز لا يُسلسَل للكونسول أبدًا**.
- **i18n**: namespace جديد `public` كامل + مفاتيح الإعدادات/أنواع الغرف/الحجوزات — تكافؤ **1761=1761=1761** (ar/en/tr) + RTL/LTR على كل الصفحات العامة.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/public_site/{__init__,apps,services,views,urls,tests}.py` + migrations `hotels.0002`/`rooms.0002`/`reservations.0004` · **جديدة (Frontend):** `app/api/public/[...path]/route.ts` · `app/hotels/page.tsx` · `app/hotels/[slug]/page.tsx` · `app/booking/manage/page.tsx` · `components/public/{PublicShell,PublicHotelCard,PublicBookingPanel}.tsx` · `lib/api/public.ts` · والوثيقة `docs/PUBLIC_WEBSITE_BOOKING_STRATEGY.md`.
- **معدّلة (Backend):** `apps/hotels/models.py` · `apps/rooms/{models,serializers}.py` · `apps/reservations/{models,serializers}.py` · `config/settings/base.py` (throttle rates) · `config/urls.py`.
- **معدّلة (Frontend):** `app/page.tsx` (صفحة عامة بدل redirect) · `app/hotel/settings/page.tsx` · `components/hotel/rooms/RoomTypesTab.tsx` · `components/hotel/reservations/ReservationsTab.tsx` · `lib/api/{types,rooms}.ts` · `styles/globals.css` · قواميس ar/en/tr · التوثيق (README، DEVELOPMENT_RULES §8l، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **633/633 OK** (593 سابقة + 40 لـ public_site) — انحدار صفر |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (المسارات `/`، `/hotels`، `/hotels/[slug]`، `/booking/manage`، `/api/public/[...path]` مبنية) |
| فحص حيّ End-to-End (عبر BFF العام) | ✅ **22/22**: نشر Ops Hotel 10 من الإعدادات → ظهر في القائمة والتفاصيل (بلا أي تسرب داخلي) → توفر 2 → حجز عام 201 (**R00001**، `held` + رمز لمرة واحدة) → التوفر هبط إلى 1 → إدارة بالرمز الصحيح 200 · رمز خاطئ 404 · مرجع خاطئ 404 (متطابقان) → طلب إلغاء ✓ → الكونسول رأى `source=public_website` + السبب (**بلا hash**) → تأكيد عبر سير العمل القائم → الزائر رأى `confirmed` → Overbooking **409** · حجب الحجز **403** · إلغاء الإدراج أخفى الفندق (قائمة 0 + 404) → **لا فوليو/دفعة/فاتورة** أُنشئت — والصفحات الأربع تعرض 200 |

### ملاحظات وقرارات
- مدة الحجز المعلّق **72 ساعة** (`PUBLIC_HOLD_HOURS`) — قرار موثّق في الوثيقة الاستراتيجية؛ دلالات انتهاء `held` من Phase 6 تسري كما هي.
- مفتاح `allow_public_booking` (من Phase 4) نُقل في واجهة الإعدادات إلى قسم «الموقع العام» الجديد لتجميع كل مفاتيح النشر في مكان واحد (بلا تغيير في الـ API).
- تسمية `public_website` أُضيفت لقواميس المصادر **عرضًا فقط**؛ خيارات نموذج الإنشاء الداخلي بقيت بلا تغيير (direct/phone/walk_in/other).
- إصلاح عرضي: سطرا README وdocs/README من Phase 14 كانا يقولان «13 نوع حدث» — صُحّحا إلى 14 وفق ملاحظة اعتماد المالك (فرق لصالح التنفيذ).

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا بوابة دفع/Stripe/PayPal · لا حسابات عملاء/تسجيل دخول للنزلاء · لا ولاء/كوبونات · لا Marketplace/SEO متقدم · لا مدونة · لا تقييمات/مراجعات · لا OTA/Channel manager · لا WhatsApp/Email/SMS/Push/Chat · لا طلبات خدمات عامة/QR menu.** **لم تبدأ Phase 16.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-09** بعد Final Acceptance Review لـ PR #14 (commit `1940972` على `origin/main@ac3472a`، mergeable_state: clean، backend 633/633، frontend lint/typecheck/build ناجحة، والبنود الـ44 المقبولة رسميًا في رسالة الاعتماد — مع الملاحظتين غير المانعتين: تصحيح 13→14 نوع حدث توثيقي متوافق مع اعتماد Phase 14، وwarnings ترقيم صفحات ServiceOrder سابقة للمرحلة).
- ملاحظة الاعتماد: «تم اعتماد Phase 15 بعد Final Acceptance Review. المرحلة أضافت الموقع العام والحجز العام الأساسي عبر public APIs تحت /api/v1/public/، مع قائمة فنادق منشورة، صفحة فندق عامة، فحص توفر باستخدام AvailabilityService، إنشاء حجز عام مدمج مع Reservation الحالي، وإدارة حجز عامة عبر reference + manage token آمن مخزن hash فقط. الحجز العام يمنع overbooking، ويستخدم booking_kind=future، والحالة الافتراضية held مع hold_expires_at = 72h، ولا ينشئ Payment أو Invoice أو Folio أو Stay. تم منع تسريب البيانات الداخلية وحماية public_manage_token_hash، وربط الحجز العام بكونسول الفندق بأمان. لا Payment Gateway، لا Customer Accounts، لا WhatsApp/Email/SMS/Push/Chat، لا OTA/Channel Manager، لا Marketplace advanced، ولا Phase 16.»
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 16 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 16 — Platform Owner Panel Completion
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-09 · اكتملت (تنفيذ) 2026-07-09 · تاريخ الاعتماد: 2026-07-09
- الهدف: إكمال لوحة صاحب المنصة — فنادق وباقات واشتراكات وتجربة مجانية وإعدادات الموقع العام وتقييد العمليات عند غياب اشتراك فعال — **بلا أي بوابة دفع**.
- الأساس: بُنيت من **`origin/main`** (0350ae9، بعد دمج Phase 15 عبر PR #14).

### ما نُفّذ (Backend)
- **إعادة استخدام أولًا:** لم يُعَد بناء شيء من Phase 3 — وُسِّع الموجود: `SubscriptionPlan` **+4 فقط** (`price_yearly` · `is_public` · `max_public_bookings_per_month` · `notes`؛ mapping موثّق: slug=الكود، price=سعر الدورة، room/user_limit=الحدود، feature_codes=الميزات) · `Hotel` **+3 تدقيق** (`suspension_reason` · `status_changed_at` · `status_changed_by`) · نموذجان جديدان: **`PlatformSubscriptionPayment`** (مدفوعات يدوية: Decimal، cash/bank_transfer/manual/other، مرجع، void بسبب لا حذف، **منفصلة كليًا عن مالية الفندق** — اختبار يثبت صفر Payment فندقي) و**`PlatformPublicSettings`** (Singleton — ليست CMS).
- **دورة حياة الفندق مدقّقة:** `activate/suspend/unsuspend` أفعال صريحة — التعليق **يتطلب سببًا** ويسجّل الفاعل والوقت؛ `status` **أزيل من PATCH** (لا التفاف على التدقيق)؛ لا حذف قاسٍ (DELETE → 405)؛ التعليق لا يحذف شيئًا ويخفي الفندق عامًا (فلاتر Phase 15 القائمة).
- **دورة الاشتراك كاملة تحت `hotels/{id}/subscriptions/`:** ‏`start-trial` (**تشديد Phase 16: التجربة مرة واحدة وكأول اشتراك فقط** — تُرفض بعد أي اشتراك سابق مدفوع/منتهٍ/ملغى، `trial_already_used`) · `activate-paid` (يدوي، مع تسجيل دفعة يدوية اختيارية) · `renew` (يمدد من max(الآن، النهاية) — لا تلقائي ولا يعيد كتابة التاريخ) · `cancel` · `expire` · `history` (محفوظ بالكامل). فلتر `expiring=soon` (نافذة 14 يومًا) للقوائم.
- **Enforcement مركزي — `apps/subscriptions/enforcement.py`:** ‏`ensure_hotel_operational` نقطة الحسم الوحيدة، تستدعيها حراس الكتابة في **9 تطبيقات** (حجوزات، إقامات/check-in-out، نزلاء، مالية/دفعات/مصاريف/فواتير، طلبات خدمات وترحيلها، تنظيف/صيانة، موظفون/صلاحيات، ورديات/إقفال يومي، غرف) **+ الحجز العام** عبر `booking_open` — معلّق → `hotel_suspended` (يتقدم)؛ بلا اشتراك فعال → **`subscription_inactive`**. **Time-aware** (اشتراك حي تجاوز نهايته يحجب — لا cron). **قرار موثّق:** فندق بلا أي سجل اشتراك لا يُحجب (الفوترة تبدأ مع الإلحاق). القراءات/التقارير/الإشعارات تعمل دائمًا ولا يُحذف شيء.
- **Dashboard جديد `dashboard/`:** عدادات الفنادق (إجمالي/نشط/إعداد/معلّق) + فنادق التجربة/المدفوعة + الاشتراكات المنتهية والقريبة من الانتهاء + عدد الباقات + المنشور عامًا/المفعّل حجزه + آخر الفنادق وأحداث الاشتراك + **تقدير الإيراد الشهري المتكرر** لكل عملة (Decimal؛ السنوي ÷12؛ custom مستثنى ومَعدود) — **لا يسمى ربحًا أبدًا** (اختبار مضاد للتسمية).
- **إعدادات الموقع العام:** إظهار/إخفاء روابط وأزرار الهيدر (رئيسية/فنادق/تواصل/احجز الآن/تجربة مجانية) + **تجاوزات تسميات لكل لغة** `{ar,en,tr}` (الفارغ يعود للقواميس) + نصوص hero وأزراره + معلومات تواصل المنصة + الفوتر؛ الروابط مقيّدة بمسار داخلي أو http(s) فقط (javascript: مرفوض — مُختبر)؛ كتابة للمالك فقط وقراءة عامة آمنة عبر `GET /api/v1/public/site-settings/`.
- **حالة الاشتراك للفندق:** ‏`/api/v1/hotel/profile/` يعيد `subscription_state` (الحالة/النهاية الفعلية/الأيام المتبقية/expiring_soon/expired/suspended/write_blocked+السبب).
- **أحداث النشاط (Phase 14 معاد استخدامه):** ‏`hotel.suspended/unsuspended` + `subscription.trial_started/activated/renewed/expired/cancelled` عبر `record_activity` (فئة system → مديرو الفندق) — **بلا نظام إشعارات جديد** (مركز إشعارات لصاحب المنصة مؤجل موثّقًا — الداشبورد يعرض الأحداث الأخيرة).
- Migrations: ‏`subscriptions.0002` · `tenancy.0003` · `platform_owner.0002`.

### ما نُفّذ (Frontend)
- **Dashboard** أُرقي للنقطة الجديدة: 10 بطاقات إحصاء + بطاقة **تقدير الإيراد** (بالتلميح الموثّق) + آخر الفنادق/أحداث الاشتراك.
- **الفنادق:** أعمدة جديدة (مدينة/اشتراك/نشر عام) + فلاتر (حالة/اشتراك/نشر) + أزرار **تفعيل / تعليق (مودال سبب إلزامي) / رفع تعليق** حسب الحالة؛ **التفاصيل:** بيانات موسّعة (عدادات غرف/موظفين/حجوزات، أعلام النشر، التجربة، بانر سبب التعليق مع الفاعل) + **بطاقة الاشتراك** (بدء تجربة — معطّل إن استُخدمت — /تفعيل مدفوع/تجديد/إلغاء/إنهاء + سجل الاشتراكات + المدفوعات اليدوية) + حذف Select الحالة من نموذج التعديل.
- **الباقات:** حقول جديدة (سعر سنوي/حجوزات عامة شهريًا/عرض عام/ملاحظات داخلية) + تفعيل/تعطيل عبر النقاط الصريحة.
- **الاشتراكات:** فلتر «القريبة من الانتهاء فقط» + أزرار تجديد/إنهاء/إلغاء.
- **صفحة جديدة `/platform/public-site`:** أقسام الهيدر (مفاتيح + تسميات ×3 لغات لكل حقل) والـ hero والتواصل والفوتر — بعنصر `I18nField` مركزي؛ وعنصر جديد في سايدبار المنصة.
- **كونسول الفندق:** ‏`SubscriptionBanner` في القشرة (معلّق/منتهٍ/قريب الانتهاء بعدد الأيام) + ربط `subscription_inactive` وبقية أكواد Phase 16 برسائل مترجمة في `errors.ts` — **الواجهة UX فقط والمنع في الخلفية**.
- **الموقع العام يستهلك الإعدادات:** ‏`SiteSettingsContext` + ‏`resolvePublicText` (fallback للقواميس) — الهيدر (ظهور/تسميات + زر «احجز الآن» الجديد) والـ hero (نصوص وأزرار وروابطها) والفوتر (نص + هاتف/بريد/عنوان المنصة) — الموقع لا ينكسر أبدًا عند غياب الإعدادات.
- **i18n:** namespaces جديدان `subscriptionState` و`publicSiteAdmin` + توسعة dashboard/hotels/plans/subscriptions/nav/public — تكافؤ **1856=1856=1856** + RTL/LTR + responsive + قسم CSS صغير واحد بالتوكنات.

### الملفات المضافة/المعدّلة
- **جديدة (Backend):** `apps/subscriptions/{enforcement,tests_enforcement}.py` · `apps/platform/tests_phase16.py` · migrations ×3 · **جديدة (Frontend):** `app/platform/public-site/page.tsx` · `components/hotel/SubscriptionBanner.tsx` · `components/public/SiteSettingsContext.tsx` · والوثيقة `docs/PLATFORM_OWNER_PANEL_STRATEGY.md`.
- **معدّلة (Backend):** `apps/subscriptions/{models,services}.py` · `apps/tenancy/models.py` · `apps/platform/{models,serializers,views,urls,services,tests}.py` · `apps/common/exceptions.py` (+3) · حراس الكتابة في views لتسعة تطبيقات · `apps/public_site/{services,views,urls}.py` · `apps/hotels/views.py`.
- **معدّلة (Frontend):** `lib/api/{types,platform,public,errors}.ts` · صفحات platform الخمس القائمة · `components/layout/{AppShell,Sidebar}.tsx` · `components/public/PublicShell.tsx` · `app/page.tsx` · قواميس ar/en/tr · `styles/globals.css` · التوثيق (README، DEVELOPMENT_RULES §8m، docs/README).

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ **678/678 OK** (633 سابقة + 45 جديدة: وصول/داشبورد/فنادق/باقات/اشتراكات/مدفوعات/إعدادات عامة/**enforcement عبر 13 كتابة ممنوعة + قراءات تعمل + حجز عام**) — انحدار صفر رغم لمس حراس 9 تطبيقات |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح (مسار `/platform/public-site` مبني) |
| فحص حيّ End-to-End | ✅ **31/31**: فصل وصول (مدير مرفوض من المنصة 403 · مجهول 401 · مالك بلا عضوية مرفوض من الفندق) → داشبورد بلا «ربح» → إعدادات الموقع العام (تحديث المالك ✓ رابط javascript مرفوض 400 ✓ مدير مرفوض 403 ✓ الموقع العام يقرأها) → باقة بحقول 16 → **تفعيل مدفوع يدوي + دفعة TRX-E2E** → تجديد → حالة الفندق نشطة → **إنهاء الاشتراك** → إنشاء حجز **403 `subscription_inactive`** · القراءات والتقارير تعمل · بانر «منتهٍ» · **الحجز العام توقف** → التجربة مرفوضة بعد اشتراك سابق (**409**) → إعادة تفعيل أعادت الكتابة → **تعليق بلا سبب 400** · تعليق بسبب ✓ · مخفي عامًا 404 · `hotel_suspended` ✓ → رفع التعليق أعاد كل شيء → أحداث `hotel.suspended/unsuspended/subscription.expired` ظهرت في سجل نشاط الفندق |

### ملاحظات وقرارات
- **قرار موثّق:** فندق بلا أي سجل اشتراك لا يُحجب — التقييد يبدأ مع دورة الفوترة («بعد انتهاء التجربة»)، حفاظًا على المستأجرين القدامى وسلوك ما قبل 16.
- **تشديد بأمر المرحلة:** التجربة تُرفض بعد أي اشتراك سابق (كانت تُرفض فقط بعد تجربة سابقة).
- **تشديد:** ‏`status` أزيل من PATCH الفندق — التغيير حصريًا عبر الأفعال المدقّقة (اختبار Phase 3 حُدّث لذلك).
- تطبيق limits الباقات تشغيليًا (غرف/موظفون/حجوزات) **مؤجل موثّقًا** مع feature flags — كما في Phase 3.
- مركز إشعارات خاص بصاحب المنصة **مؤجل موثّقًا** — الأحداث تصل مديري الفندق عبر Phase 14 والداشبورد يعرض الأخيرة.
- `PlatformSubscriptionPayment` **بُني** (كان اختياريًا): بسيط جدًا ويغلق حلقة «تسجيل مرجع يدوي».

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا Payment Gateway/Stripe/PayPal/بوابة محلية · لا دفع اشتراكات إلكتروني · لا Bank reconciliation · لا Tax engine متقدم · لا Accounting ledger · لا فواتير منصة متقدمة · لا Commission engine · لا OTA/Channel manager · لا Marketplace متقدم · لا حسابات عملاء · لا WhatsApp/Email/SMS/Push · لا CRM · لا Affiliate · لا كوبونات متقدمة · لا تقييمات عامة.** **لم تبدأ Phase 17.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-09** بعد Final Acceptance Review لـ PR #15 — قرار المالك النصي: «PR #15 — Phase 16: Approved to merge ✅». المراجعة النهائية جرت على base ‏`origin/main@0350ae9` (merge-base مطابق، mergeable_state: clean)، وشملت معالجة تعليقات Copilot الأربعة: إصلاحان مانعان نُفذا في `4187f7f` (رفض الروابط protocol-relative ‏`//host` في `_validate_safe_url` + إخفاء زر «تجديد» عن اشتراكات التجربة) وملاحظتا أداء N+1 غير مانعتين وُثقتا؛ وبعد الإصلاحات: backend ‏**679/679**، frontend ‏lint/tsc/build نظيفة، فحص حي 31/31 + 7/7. نقطة «فندق بلا سجل اشتراك لا يُحجب» سلوك موثّق ومقبول (لا مسار استغلال من جهة العميل — الفوترة بيد المالك حصرًا) مع اقتراح تشديد اختياري مستقبلي بقرار المالك.
- الدمج: squash merge لـ PR #15 (كوميتا `2500bcc` + `4187f7f`) → ‏`origin/main@0de328c` بعنوان «Phase 16 — Platform Owner Panel Completion (#15)».
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 17 لا تبدأ إلا برسالتها الرسمية.**

---

## Phase 17 — Mobile / PWA / Offline / Performance
- الحالة: **مكتملة ✅** (معتمدة نهائيًا من المالك)
- التاريخ: بدأت 2026-07-09 · اكتملت (تنفيذ) 2026-07-09 · تاريخ الاعتماد: 2026-07-09
- الهدف: جاهزية احترافية على الموبايل والتابلت + أساس PWA آمن + fallback محدود لعدم الاتصال + تحسينات أداء — **بلا أي ميزة تجارية جديدة**.
- الأساس: بُنيت من **`origin/main`** (fd26448، بعد اعتماد Phase 16).

### ما نُفّذ (Mobile & Tablet)
- **جرد أولًا:** النظام المركزي كان يملك أساسًا قويًا (سايدبار Drawer ≤900px، ‏`.table-scroll` لكل الجداول، التفاف page-header/filter-bar، مودال 90dvh، ‏form-grid عمود واحد ≤560px، شبكات auto-fill، شبكات الموقع العام) — لذلك أضيفت **طبقة صقل مركزية واحدة** لا تخطيطات لكل صفحة:
- **حراسة overflow:** ‏`minmax(min(100%, 14rem), 1fr)` لشبكتي الإحصاء والتفاصيل (لا تمرير أفقي قسري على الهواتف الضيقة) + `overflow-wrap: anywhere` لقيم التفاصيل.
- **أهداف لمس** (`pointer: coarse`): أزرار/حقول/select/مبدّل اللغة ≥2.75rem وتبويبات وترقيم ≥2.5rem.
- **كتلة ≤640px:** عناوين أصغر، مودالات كالـ sheets (حواف ضيقة + footer يلتف)، خلايا جداول أكثف مع بقاء التمرير، التفاف section-header وmini-list، فلاتر بعمود واحد وأزرارها بعرض كامل، ضبط hero/هيدر/فوتر/تواريخ الحجز في الموقع العام، توست داخل الشاشة.
- **تابلت (641–900px):** صفحة الفندق العامة تكدّس لوحة الحجز تحت المحتوى بدل aside مضغوط.
- كل القواعد بالتوكنات حصرًا وبخصائص منطقية (RTL/LTR سليم) وتخدم الكونسولين والموقع العام معًا.

### ما نُفّذ (PWA)
- **`app/manifest.ts`**: الاسم «Funduqii — فندقي» + short_name + وصف + `display: standalone` + `start_url: "/"` + ألوان theme/background من التوكنات + **5 أيقونات مولّدة** (192/512 + maskable 192/512 + apple-touch 180) في `public/icons/`.
- **layout الجذري:** ‏`viewport` (device-width/scale/theme-color) + بيانات تثبيت Apple — القابلية للتثبيت مكتملة (manifest ✓ أيقونات ✓ SW ✓).
- **الممنوع لم يُبنَ:** لا Push ولا Background sync ولا اختصارات ولا أي offline للبيانات.

### ما نُفّذ (Offline fallback الآمن)
- **`public/sw.js` أدنى حد ممكن:** يخزّن مسبقًا **3 أصول عامة ثابتة فقط** (offline.html + أيقونتان)، يعترض **failed navigations فقط** ويجيب بصفحة offline؛ **كل ما عداها network-only**.
- **`public/offline.html`:** صفحة ثابتة ثلاثية اللغات (ar/en/tr معًا — لا قاموس تطبيق متاح offline) بزر إعادة محاولة، بألوان التوكنات.
- **قرارات أمنية موثقة (رفض صريح):** لا caching لأي API أو صفحة كونسول (بيانات الفنادق/النزلاء/المالية/الصلاحيات لا تدخل أي cache — لا تسرب بين مستخدمين/مستأجرين ولا بيانات قديمة بعد تبديل مستخدم/فندق) · لا tokens/JWT قرب أي cache (الجلسات HttpOnly كما هي) · **لا كتابات offline إطلاقًا** (لا حجز/check-in/دفعات/فواتير/طوابير/قاعدة محلية) — الوضع الكامل يتطلب cache واعيًا بالمصادقة ومقسّمًا بالمستأجر فوُثق تأجيله بدل بنائه ناقص الأمان.
- التسجيل عبر مكوّن صغير يفشل بصمت — لا شيء في التطبيق يعتمد على الـ SW.

### ما نُفّذ (Performance — Backend محدود وبلا كسر عقود)
- **إزالة N+1 من قائمة الفنادق العامة** (ملاحظة مراجعة PR #15): جواب الاشتراك لبطاقات حتى 60 فندقًا صار **دفعة واحدة** (`subscription_blocked_hotel_ids` — استعلامان إجمالًا بدل اثنين لكل فندق) والوسائط عبر `prefetch_related` واحد (+تعديل `hotel_media_payload` للترشيح في Python) — و`booking_open` بالقاعدة ذاتها مع **اختبار تكافؤ** يقارن الدفعة بالفحص الفردي عبر 6 حالات اشتراك.
- **قائمة فنادق المالك:** ‏`select_related("settings", "status_changed_by")` (JOIN واحد بدل استعلامين لكل صف — ملاحظة PR #15 الثانية).
- **فهرس `HotelSubscription (hotel, status)`:** ‏enforcement ‏Phase 16 يستشير هذا الزوج في **كل** طلب كتابة — صار مفهرسًا (migration ‏`subscriptions.0003`).
- الواجهة: الصور العامة lazy أصلًا وحالات التحميل/الخطأ/الفراغ مركزية أصلًا — لا مكتبات جديدة ولا تغيير معماري ولا تغيير أي contract.

### الملفات المضافة/المعدّلة
- **جديدة:** `frontend/src/app/manifest.ts` · `frontend/src/components/PwaRegistration.tsx` · `frontend/public/{sw.js,offline.html}` · `frontend/public/icons/` (5 أيقونات) · `docs/MOBILE_PWA_PERFORMANCE_STRATEGY.md` · migration `subscriptions.0003` (فهرس).
- **معدّلة:** `frontend/src/styles/globals.css` (قسم Phase 17 + حارسا الشبكتين) · `frontend/src/app/layout.tsx` (viewport/apple + تسجيل SW) · `backend/apps/subscriptions/{models,enforcement,tests_enforcement}.py` · `backend/apps/public_site/{services,views}.py` · `backend/apps/platform/views.py` · التوثيق (README، DEVELOPMENT_RULES §8n، docs/README).
- **الترجمة:** لا مفاتيح جديدة لزمت (صفحة offline ثابتة ثلاثية اللغات بالتصميم) — تكافؤ ar/en/tr باقٍ **1856=1856=1856**.

### الفحوصات والنتائج
| الفحص | النتيجة |
|---|---|
| `manage.py check` | ✅ لا مشاكل |
| `makemigrations --check` | ✅ No changes detected |
| `manage.py test` | ✅ الحزمة الكاملة ناجحة (بما فيها المصادقة والصلاحيات والحجوزات وcheck-in/out والدفعات والخدمات والتنظيف والورديات والتقارير والإشعارات والحجز العام وenforcement الاشتراك + اختبار تكافؤ الدفعة الجديد) |
| Frontend `lint` / `tsc --noEmit` / `build` | ✅ الكل ناجح |
| فحص حيّ | ✅ ‏`manifest.webmanifest` ‏200 بمحتواه الكامل (الاسم/standalone/الألوان/4 أيقونات) · ‏`sw.js` و`offline.html` والأيقونات 200 · روابط الـ head (viewport/theme-color/manifest/apple-touch) في الصفحة المقدَّمة · صفحات الموقع العام والدخول 200 |

### ملاحظات وقرارات
- خط الأمان في offline (لا بيانات، لا tokens، لا كتابات) قرار موثّق في الوثيقة و§8n — الوضع الكامل مؤجل بقرار لا نقصًا.
- ملاحظتا الأداء غير المانعتين من مراجعة PR #15 عولجتا هنا ضمن نطاق Phase 17 المسموح (تحسين query واضح).
- المؤجل موثّقًا: offline كامل مقسّم بالمستأجر · Push · جداول virtualized للبيانات الضخمة · خط أنابيب لتحسين صور الفنادق المرفوعة.

### ما لم يُنفَّذ (خارج المرحلة، عمدًا)
- **لا Payment Gateway/Stripe/PayPal · لا حسابات عملاء · لا WhatsApp/Email/SMS/Push · لا OTA/Channel Manager · لا Marketplace/CRM/Coupons/Payroll/Accounting/Inventory/POS المتقدمة · لا offline للبيانات أو العمليات.** **لم تبدأ Phase 18.**

### الاعتماد
- **معتمدة نهائيًا من المالك بتاريخ 2026-07-09** بعد Final Acceptance Review لـ PR #16 — قرار المالك النصي: «PR #16 — Phase 17: Approved to merge ✅». المراجعة جرت على base ‏`origin/main@fd26448` (merge-base مطابق، mergeable_state: clean) وشملت معالجة تعليقات Copilot الأربعة على الـ PR في كوميت `9180906` (‏Response احتياطي في sw.js حتى لا يرفض respondWith عند فقدان الـ cache · سمات `lang` لأقسام offline.html الثلاثة · ‏Prefetch مرشّح بالوسائط النشطة للقائمة العامة · فرع واعٍ بالـ cache في hotel_media_payload — مع اختبار جديد يثبت استبعاد الوسائط غير النشطة على المسارين)؛ وبعد الإصلاحات: backend ‏**681/681**، frontend ‏lint/tsc/build نظيفة، فحوص PWA الحية كاملة، ومعاينات بصرية موبايل/ديسكتوب للصفحات العامة نظيفة، مع إصلاح توثيقي سابق لجدول المراحل في `2f015a8`.
- الدمج: squash merge لـ PR #16 (كوميتات `3db06ef` + `2f015a8` + `9180906`) → ‏`origin/main@c16c746` بعنوان «Phase 17 — Mobile / PWA / Offline / Performance (#16)».
- ملفات OpenWolf/Graphify محلية فقط ولم تدخل Git؛ استُخدمت الأداتان كمساعدة فقط لا كمصدر قرار. **Phase 18 لا تبدأ إلا برسالتها الرسمية.**

---

## Task — App Shell: ثلاث بطاقات مستقلة (سايدبار / توب بار / محتوى)
- الحالة: **بانتظار الاعتماد 🔎** (مهمة صغيرة — ليست مرحلة)
- التاريخ: 2026-07-09 · الأساس: `origin/main@dddc09a`
- **البنية المنفذة:** الشاشة بخلفية `--color-bg` وحاشية عامة، وداخلها **ثلاث بطاقات منفصلة** بفجوات متسقة: بطاقة السايدبار (sticky بارتفاع مضبوط `calc(100dvh - 2×gap)` وتمرير داخلي، حد كامل + `radius-xl` + ظل) · بطاقة التوب بار (sticky بإزاحة الفجوة، حد كامل + `radius-xl` + خلفية blur — الجرس واللغة والحساب كما هي) · **بطاقة المحتوى** (`content-container` صارت بطاقة surface بحد وradius وظل، `flex:1` لملء الطول، والحشوة الداخلية من `page-container` القائمة).
- **متغير واحد `--shell-gap`** (‏`space-3`) يقود الحاشية العامة والفجوات كلها معًا — ويتقلص تلقائيًا إلى `space-2` تحت 900px.
- **الموبايل:** السايدبار يعود drawer كامل الارتفاع بزوايا مستديرة على حافته الخلفية فقط (خصائص منطقية — RTL سليم)، والتوب بار والمحتوى بطاقتان متراصتان بفجوة.
- **قيود محترمة:** صفر تغيير في قائمة السايدبار أو تسمياتها أو الصلاحيات أو الحراس أو منطق الأعمال؛ الإشعارات باقية بالجرس فقط؛ **CSS خالص** (صفر TSX/Backend)؛ لوحة المالك تستفيد تلقائيًا (نفس القشرة)؛ نموذج تمرير النافذة أُبقي عمدًا حفاظًا على قواعد الطباعة (`print-doc`).
- **إصلاح المراجعة البصرية (بطلب المالك):** (أ) **سكرول السايدبار المزعج** — سببه `overflow-y: auto` مع الارتفاع المحسوب فيظهر شريط رمادي دائم بين السايدبار والمحتوى؛ الحل: إخفاء الشريط بصريًا (`scrollbar-width: none` + ‏`::-webkit-scrollbar`) مع بقاء التمرير عاملًا على الشاشات القصيرة — لا عنصر يُخفى ولا قائمة تتغير؛ (ب) **ضيق المحتوى والفراغات الجانبية** — سببه `max-width: 84rem + margin auto` الموروثان في `content-container` (كانا غير مرئيين قبل تحويله لبطاقة)؛ الحل: البطاقة صارت **fluid بعرض العمود كاملًا** (`width:100%; max-width:none`) فتحاذي التوب بار تمامًا وتستفيد الجداول من الشاشة؛ (ج) **الحشوة المتراكمة** — ‏`page-container` خُفضت من `--space-8` (‏2rem) إلى `--space-5 --space-4` على الديسكتوب و`--space-3` على الموبايل.
- **تحسينات المراجعة البصرية الثانية (بطلب المالك):** (أ) **مبدّل اللغة** أعيد بناؤه كقائمة مخصصة أنيقة (`LanguageSwitcher`): زر pill هادئ يعرض اللغة الحالية + قائمة منسدلة مصممة (خيارات بعلامة ✓ للنشطة، إغلاق بالنقر الخارجي/Escape) بدل select البدائي — الوظيفة وi18n وRTL/LTR كما هي؛ (ب) **زر تسجيل الخروج** صار أحمر واضحًا غير فاقع عبر متغير مركزي جديد `dangerSoft` في Button (نص أحمر على غسلة حمراء خفيفة بإطار ناعم) — منطق الخروج بلا مساس؛ (ج) **فتحة العلامة في رأس السايدبار صارت هوية الفندق الديناميكية**: لوغو الفندق المرفوع من إعداداته (عبر `profile.logo` القائم — **صفر Backend جديد**) وإلا Monogram أنيق من أحرف اسم الفندق، مع اسم الفندق كسطر رئيسي و«Funduqii» كسطر فرعي؛ لوحة المالك تحتفظ بعلامة المنتج؛ **زر القائمة الوظيفي للموبايل بقي زرًا مستقلًا في التوب بار** كما كان. ولتفادي تكرار الجلب أُنشئ `HotelProfileContext` مشترك (تحميل واحد للقشرة يغذي الهوية وبانر الاشتراك معًا).
- **تصحيح توزيع الهوية (بطلب المالك):** ‏**السايدبار = هوية المنصة فقط** (علامة Funduqii + الاسم «فندقي/Funduqii» + القائمة الرسمية — لا لوغو فندق ولا اسمه ولا مستخدم ولا خروج ولا إشعارات)؛ ‏**التوب بار = هوية الفندق + أدوات المستخدم**: لوغو الفندق من إعداداته (‏`profile.logo` القائم — صفر Backend) أو Monogram أنيق من اسم الفندق (أو أيقونة فندق إن غاب الاسم لحظيًا) + اسم الفندق في بداية الشريط، ثم الجرس واللغة وشريحة المستخدم والخروج الأحمر في نهايته؛ الاسم الفندقي يصل فوريًا من الخادم (fallback prop) ويُخفى نصه على ≤420px مع بقاء العلامة؛ **لوحة المالك بلا هوية فندق** (لا سياق فندق) وتحتفظ بعنوانها العام — مُتحقق بجلستين مصادَقتين (مدير فندق + مالك منصة).
- **نقل معلومات المستخدم إلى التوب بار (بطلب المالك):** أزيل كرت المستخدم (الاسم + الإيميل + avatar) من أسفل السايدبار كليًا بلا مساحة محجوزة — السايدبار صار هوية الفندق + القائمة الرسمية فقط؛ وفي التوب بار **شريحة مستخدم** صغيرة أنيقة (avatar دائري 1.75rem بحرف الاسم + الاسم فقط — **بلا إيميل**) بين مبدّل اللغة وزر الخروج الأحمر؛ على ≤640px يُخفى الاسم ويبقى الـ avatar؛ فتحة الـ avatar مصممة لاستبدال الحرف بصورة بروفايل مستقبلًا (**بلا upload/backend/صفحة بروفايل الآن**).
- **الفحوصات:** ‏lint ✅ · tsc ✅ · build ✅ · تحقق **بجلسة مصادَقة** على `/hotel/rooms`: البنية الثلاثية + `lang-menu` + الخروج `dangerSoft` + شريحة `topbar-user` بالاسم بلا إيميل + زوال كرت السايدبار — كلها في الـ HTML المقدَّم؛ والمعاينة البصرية النهائية متاحة للمالك على الخوادم المحلية.
- **الاعتماد:** بانتظار قرار المالك — لا دمج ولا اعتماد ذاتي.

---

## Task — إعادة تنظيم سايدبار لوحة الفندق (تسميات + فصل الأقسام المدمجة)
- الحالة: **مكتملة ✅** (معتمدة من المالك — مهمة صغيرة، ليست مرحلة)
- التاريخ: 2026-07-09 · الأساس: `origin/main@b610336` (Phase 17 مدموجة قبل البدء ✅) · تاريخ الاعتماد: 2026-07-09
- **الاعتماد والدمج:** قرار المالك النصي: «PR #18 — Hotel Sidebar Reorg: Approved to merge ✅» بعد Final Acceptance Review (التسميات 45/45 حرفيًا، الحماية مثبتة بمحاكاة 19/19، وتعليقا Copilot: الأول سلوك مقصود موثق والثاني عولج في `6682350`). الدمج: squash لـ PR #18 (كوميتا `591d9c4` + `6682350`) → ‏`origin/main@64bfbdf`. **Phase 18 لم تبدأ.**
- **القائمة الرسمية المنفذة (15 عنصرًا بالترتيب):** الغرف والطوابق → الحجوزات → الدخول والمغادرة → النزلاء → التدبير الفندقي → المطعم والكافتيريا → فوليو النزيل → المصروفات → الموظفون → الورديات → الإغلاق اليومي → المالية → التقارير → الاشتراك والباقات → الإعدادات.
- **الفصل:** «فوليو النزيل» و«المصروفات» و«المالية» ثلاثة عناصر مستقلة تفتح تبويبات صفحة المالية المشتركة عبر deep-link ‏`?tab=` (folios/expenses/النظرة العامة)؛ «الورديات» و«الإغلاق اليومي» عنصران مستقلان على صفحة الورديات (`?tab=dailyClose`) — الصفحات والخدمات الداخلية كما هي، والتبويب الداخلي يزامن الـ URL ليبقى تفعيل السايدبار صادقًا.
- **الإشعارات أزيلت من السايدبار فقط:** المسار وroute guard والصفحة كما هي، والوصول حصريًا من جرس التوب بار (لم يُمس).
- **جديد:** صفحة **`/hotel/subscription` للقراءة فقط** (بيانات `subscription_state` القائمة من profile — الباقة/الحالة/النهاية/الأيام المتبقية + بانرات القيود + ملاحظة أن التفعيل والتجديد من إدارة المنصة) — **بلا أي دفع إلكتروني**، وإدارة الباقات تبقى بلوحة المالك حصريًا.
- **الصلاحيات (Phase 11 محفوظة):** كل عنصر يظهر بصلاحيته القائمة — فوليو النزيل/المالية = `finance.view`، المصروفات = `expenses.view`، الورديات = `shifts.view`، الإغلاق اليومي = `daily_close.view` (تجاوز access لكل عنصر منفصل؛ **لا صلاحيات جديدة اختُرعت**)؛ صفحة الاشتراك بلا صلاحية (نفس معلومات البانر التي يراها كل عضو — قرار موثق)؛ حارس المسارات وX-Hotel-ID ولوحة المالك بلا مساس.
- **الترجمات:** namespace جديد `sidebar` (15) + `hotelSubscription` (10) بالنصوص الرسمية المطلوبة — تكافؤ **1881=1881=1881**.
- **Backend: لم يُعدَّل إطلاقًا.**
- **إصلاح المراجعة (بطلب المالك):** التبويبات الداخلية للصفحتين المشتركتين صارت **permission-aware** — ‏FinancePanel: تبويبات النظرة/الفوليو/الدفعات/الفواتير خلف `finance.view` والمصروفات خلف `expenses.view`؛ ‏ShiftsPanel: تبويبات الورديات خلف `shifts.view` والإغلاق اليومي خلف `daily_close.view` (الأكواد القائمة حصرًا). التبويب غير المسموح لا يُعرض ولا يُفتح برابط مباشر (`?tab=` غير المسموح يُحسم لأول تبويب مسموح ويُطبَّع الـ URL — الـ URL مصدر الحقيقة الوحيد فلا loop)، ومن بلا أي صلاحية يرى Access denied القائمة. **إثبات كودي موثق: 19/19 حالة** (المستخدم محدود الصلاحية بكل نوع، الروابط المباشرة المهاجمة، المدير، الجمع بين الصلاحيتين، صفر صلاحيات بلا crash، ونقطة ثبات التطبيع).
- **الفحوصات:** ‏lint ✅ · tsc ✅ · build ✅ (`/hotel/subscription` في الشجرة) · الجرس سليم · المسارات تستجيب خلف بوابة الجلسة · القواميس الثلاث متكافئة · محاكاة صلاحيات التبويبات 19/19.
- **الاعتماد:** بانتظار قرار المالك — لا دمج ولا اعتماد ذاتي.
