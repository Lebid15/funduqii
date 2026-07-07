# Funduqii / فندقي — Progress Log (سجل تنفيذ المراحل)

> **الغرض:** مرجع موثّق يبيّن ماذا نُفّذ في كل مرحلة من مراحل المشروع، ونتيجة كل مرحلة، والتواريخ، وما تبقّى.
> **قاعدة التحديث:** بعد إغلاق أي مرحلة، أضِف قسمها هنا (أو حدّثه) قبل بدء المرحلة التالية.
> **المرجعان الأساسيان:** [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md) (خطة المشروع) و [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) (قواعد التطوير).
> **حالة الاعتماد:** لا تُعلَّم مرحلة «مكتملة ✅» إلا بعد اعتماد المالك. المراحل المنفَّذة والمُختبَرة بانتظار المراجعة تُعلَّم «بانتظار الاعتماد 🔎».
> **آخر تحديث:** 2026-07-07

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
| 6 | Reservations + Availability Engine | بانتظار الاعتماد 🔎 | 2026-07-07 |
| 7 | Guests + Check-in + Check-out | لم تبدأ ⏳ | — |
| 8 | Payments + Expenses + Folio + Invoices | لم تبدأ ⏳ | — |
| 9 | Restaurant + Cafeteria | لم تبدأ ⏳ | — |
| 10 | Housekeeping + Maintenance + Lost & Found | لم تبدأ ⏳ | — |
| 11 | Shifts + Daily Close | لم تبدأ ⏳ | — |
| 12 | Public Website + Public Booking | لم تبدأ ⏳ | — |
| 13 | Reports + Notifications + Audit Logs | لم تبدأ ⏳ | — |
| 14 | Full Testing + Production Readiness | لم تبدأ ⏳ | — |

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
- الحالة: 🔎 **بانتظار الاعتماد** (منفَّذة ومُختبَرة — لم تُعتمد ذاتيًا)
- التاريخ: بدأت 2026-07-07 · اكتملت (تنفيذ) 2026-07-07
- الهدف: نظام الحجوزات الداخلي للفندق + **محرك توفر مركزي يمنع overbooking**، **بلا** check-in/out ولا نزلاء كاملين ولا مال ولا موقع عام.

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
- **لا check-in/check-out · لا `occupied` · لا Guest profile/وثائق · لا payments/folio/invoices/expenses · لا مطعم/تنظيف-صيانة workflows · لا ورديات/إغلاق يومي/تقارير · لا موقع عام/حجز عام · لا واتساب/خرائط فعلية.** `ReservationRoomAssignment` مؤجّل لـ Phase 7. **لم تبدأ Phase 7.**

### الاعتماد
- **بانتظار اعتماد المالك** عبر مراجعة PR. **لم تُعتمد ذاتيًا.** لا يُغيَّر وضع Phase 7.
