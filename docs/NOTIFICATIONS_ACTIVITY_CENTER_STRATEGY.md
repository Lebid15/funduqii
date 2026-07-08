# Notifications + Activity Center — Phase 14 Strategy

هذه الوثيقة تشرح قرارات Phase 14: مركز إشعارات **داخلي** وسجل نشاط تشغيلي
مبسط داخل الفندق — بلا أي قناة خارجية.

## لماذا ليست WhatsApp / Email / Push؟

القنوات الخارجية تجرّ معها إعدادات مزوّدين وقوالب وموافقات وتسليمًا وفشلًا
وإعادة محاولات — بنية تحتية كاملة لا يحتاجها الأساس. Phase 14 تجيب سؤالًا
واحدًا: **ماذا يحتاج انتباهي داخل النظام الآن؟** فالإشعار يعيش في الواجهة
فقط، وأي قناة خارجية مستقبلية ستُبنى فوق نفس ActivityEvent دون تغيير مخطط.

## النموذجان

### ActivityEvent (ACT00001)
حدث تشغيلي واحد: نوع (`payment.recorded`…)، تصنيف (11 فئة)، خطورة
(info/success/warning/danger)، عنوان/رسالة، فاعل ومستهدَف اختياريان، مرجع
كائن، رابط داخلي، وmetadata مُنظَّفة.

- **سجل تشغيلي مبسط للواجهة** — ليس Audit Log قانونيًا وليس بديلًا عن
  سجلات الحالة لكل نموذج (تلك باقية كما هي).
- append-only: لا تعديل ولا حذف (لا DELETE إطلاقًا).

### Notification (NTF00001)
إشعار موجّه **لعضو واحد**: مستلم، مرجع الحدث، تصنيف/خطورة/عنوان/رسالة/رابط،
وحالتا `is_read`/`is_archived` بطوابعهما.

- **صندوق وارد خاص**: المستخدم يرى إشعاراته فقط؛ المدير يرى الصورة الأوسع
  عبر مركز النشاط لا عبر صناديق الآخرين (اختبار صريح: 404 على إشعار الغير).
- **NotificationPreference أُجّل عمدًا** (خيار المواصفة المفضل): الافتراضيات
  المبنية على الصلاحيات كافية الآن؛ أي تفضيلات لاحقة طبقة فوق نفس البنية.

## المسار الوحيد للإنشاء

`apps.notifications.services.record_activity` هو المدخل الأوحد: خدمات النطاق
(حجوزات/إقامات/مال/خدمات/تشغيل/ورديات/موظفون) تستدعيه بعد نجاح كتابتها
(استيراد كسول). لا view ينشئ حدثًا مباشرة.

### أمان المحتوى
- **metadata_json**: تُمرَّر عبر `safe_metadata` — تُسقط أي مفتاح يحوي
  password/token/secret/authorization/api_key، وتُبقي القيم البدائية فقط
  (اختبار صريح).
- **related_url**: عبر `safe_related_url` — مسار داخلي يبدأ بـ `/` حصرًا؛
  `https://…`، `//…`، و`javascript:` كلها تُفرَّغ (اختبار صريح).

## منطق المستلمين

`eligible_recipients(hotel, category)`:
1. عضويات **الفندق نفسه** النشطة بمستخدمين نشطين فقط.
2. **المدير دائمًا** + الموظف الحامل صلاحية عرض مطابقة للفئة
   (خريطة `CATEGORY_VIEW_CODES`: finance→finance.view/expenses.view،
   operation→housekeeping/maintenance/lost_found.view، shift→shifts/daily_close.view،
   reservation/stay→reservations/stays.view… إلخ).
3. `system`/`report` → **المديرون فقط**.
4. **الفاعل لا يُشعَر بفعله** (تقليل ضجيج — موثّق).
5. الموظف المعطّل، فندق آخر، مالك المنصة بلا عضوية: **لا شيء أبدًا**
   (اختبارات لكلٍّ منها). التكرار ممنوع بمجموعة seen.

## الأحداث المربوطة الآن (13 نوعًا — تغطي المجموعة الإلزامية كاملة)

`reservation.created/cancelled` · `stay.checked_in/checked_out` ·
`payment.recorded/voided` · `service_order.posted_to_folio` ·
`housekeeping.task_created/task_completed` ·
`maintenance.request_created/request_resolved` · `shift.closed`
(warning عند فرق صندوق) · `daily_close.closed` · `staff.permissions_updated`
(بمستهدَف).

### المؤجل من الأحداث (موثّق)
`reservation.confirmed/no_show` · `room.marked_dirty` · `lost_found.*` ·
`expense.created/voided` · `invoice.issued` · `folio.closed` ·
`service_order.created/delivered/cancelled` · `shift.opened` · `handover.*` ·
`staff.created/deactivated/reactivated` — تُضاف لاحقًا بسطر استدعاء واحد لكل
حدث دون أي تغيير مخطط.

## الرؤية والصلاحيات

- السجل المركزي: `notifications.view/update` + `activity.view/view_all`.
- **الإشعارات**: view للقراءة؛ update لعمليات المستلم (قراءة/الكل/أرشفة).
- **مركز النشاط**: المدير أو حامل `activity.view_all` يرى كل نشاط الفندق؛
  حامل `activity.view` فقط يرى **فئات صلاحياته + الأحداث التي كان فاعلها أو
  المستهدَف بها** (قاعدة موثقة ومختبَرة — ولهذا يرى الموظف حدث تحديث
  صلاحياته هو حتى بلا staff.view).
- عزل كامل بين الفنادق في كل مسار.

## الفندق المعلّق

القراءة (إشعارات/نشاط/عدادات) متاحة بحسب الصلاحيات، **وكذلك
قراءة/أرشفة الإشعارات** — قرار موثّق: هذه حالة مستخدم صرفة (أعلام على صندوقه
الخاص) لا كتابة تشغيلية. لا توجد أي كتابة تشغيلية في التطبيق أصلًا.

## الواجهة

- **جرس Topbar** (نُفِّذ): شارة غير المقروء لواجهة الفندق، تُحمَّل **مرة واحدة**
  عند فتح القشرة — لا realtime ولا polling (عمدًا)؛ يختفي كليًا بلا
  `notifications.view`؛ النقر ينقل إلى الصفحة.
- `/hotel/notifications` بثلاثة تبويبات: نظرة عامة (6 بطاقات) · الإشعارات
  (فلاتر تصنيف/خطورة/تاريخ + غير المقروء/المؤرشفة، قراءة/الكل/أرشفة/فتح
  الرابط) · مركز النشاط (فلاتر + فاعل/وقت/نوع مترجم بfallback آمن).
  **لا تبويب تفضيلات** (Preferences مؤجلة). المسار خلف
  `notifications.view|activity.view` في خريطة الوصول، والتبويبات تُخفى
  بصلاحياتها.
- مكونات مركزية فقط، **صفر CSS جديد**، ترجمات ar/en/tr كاملة، RTL/LTR،
  حالات موحّدة. عناوين/رسائل الأحداث بيانات سجل (كملاحظات سجلات الحالة)؛
  الواجهة تترجم التسميات (النوع/التصنيف/الخطورة).

## المؤجل عمدًا

WhatsApp · Email · SMS · Push · Chat وMentions وComment threads ·
WebSocket/realtime متقدم · جدولة إشعارات وقوالب خارجية · حملات تسويق ·
رسائل نزلاء عامة · NotificationPreference · Audit Log قانوني/SIEM ·
بقية الأحداث المذكورة أعلاه.
