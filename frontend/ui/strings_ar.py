"""Centralized user-facing strings — Arabic.

Every user-visible string in the application lives here; widgets never
hardcode text.  The file is organized into 22 thematic sections so that
translators and developers can find any string by feature area.

Sections
--------
 1. عام                                2. أخطاء تقنية
 3. الترخيص والتحديثات                 4. المصادقة
 5. الجولة الإرشادية                    6. شريط العنوان
 7. التنقل                             8. مستويات الأسعار والتعبئة
 9. نقطة البيع                        10. الدفع
11. إغلاق الصندوق                     12. العملاء
13. سجل المبيعات                      14. المرتجعات
15. المخزون والجرد                    16. بطاقة المنتج
17. حركات المخزون والتعديل            18. الموردون والمشتريات
19. الإحصائيات ولوحة التحكم           20. التنبيهات والديون
21. الإعدادات                         22. النسخ الاحتياطي، الملصقات،
                                          الاستيراد، التصدير والترقيم
"""

# ======================================================================
# 1. عام
# ======================================================================

APP_TITLE = "إدارة المخزون ونقاط البيع"

OK = "تأكيد"
CANCEL = "إلغاء"
CLOSE = "إغلاق"
SAVE = "حفظ"
DELETE = "أرشفة"
EDIT = "تعديل"
SEARCH = "بحث…"
REFRESH = "تحديث"
YES = "نعم"
NO = "لا"
ACTION_CLOSE = "إغلاق"

CONFIRM_TITLE = "تأكيد"
ERROR_TITLE = "خطأ"
INFO_TITLE = "معلومات"
REQUIRED_FIELD = "هذا الحقل إلزامي."
LOADING = "جاري التحميل"
PIN_REQUIRED_ACTION = (
    "يتطلب هذا الإجراء رمز PIN الخاص بالمالك. " "أعد تشغيل التطبيق وأدخل رمز PIN."
)

# ======================================================================
# 2. أخطاء تقنية
# ======================================================================

API_STARTUP_ERROR_TITLE = "خطأ في بدء التشغيل"
API_STARTUP_ERROR_TEXT = (
    "تعذر بدء تشغيل الخدمة المحلية. " "يرجى إغلاق التطبيق ثم إعادة تشغيله."
)
NETWORK_ERROR = (
    "الخدمة المحلية لا تستجيب. " "يرجى الانتظار بضع ثوانٍ ثم المحاولة مرة أخرى."
)
UNEXPECTED_ERROR = "حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى."
VERSION_MISMATCH_TITLE = "إصدار غير متوافق"
VERSION_MISMATCH_TEXT = (
    "هذه الواجهة (الإصدار {frontend}) غير متوافقة مع الخدمة المحلية "
    "(الإصدار {api}، الحد الأدنى المطلوب: الإصدار {min_fe}). "
    "يرجى تحديث التطبيق."
)

# ======================================================================
# 3. الترخيص والتحديثات
# ======================================================================

LICENSE_ERROR_TITLE = "خطأ في الترخيص"
LICENSE_MISSING = "ملف الترخيص غير موجود. يرجى وضع ملف license.lic في مجلد التطبيق."
UPDATE_AVAILABLE = "يتوفر إصدار جديد ({version})!"
UPDATE_AVAILABLE_HINT = "قم بتنزيله من: {url}"

# ======================================================================
# 4. المصادقة
# ======================================================================

# --- الإعداد الأول
ONBOARDING_TITLE = "مرحبًا بك في إدارة المخزون ونقاط البيع"
ONBOARDING_WELCOME = "الإعداد الأول"
ONBOARDING_DESC = (
    "يرجى تعيين رمز PIN (كلمة مرور) لحماية الوصول إلى نقطة البيع الخاصة بك. "
    "سيُطلب هذا الرمز عند كل تشغيل."
)
ONBOARDING_PIN_PROMPT = "تعيين رمز PIN:"
ONBOARDING_PIN_CONFIRM = "تأكيد رمز PIN"
ONBOARDING_SUBMIT = "البدء"
ONBOARDING_ERR_EMPTY = "لا يمكن أن يكون رمز PIN فارغًا."
ONBOARDING_ERR_MISMATCH = "رمزا PIN غير متطابقين."

# --- الاتصال / PIN
LOGIN_TITLE = "رمز PIN"
LOGIN_PROMPT = "أدخل رمز PIN لفتح التطبيق:"
LOGIN_PLACEHOLDER = "رمز PIN"
LOGIN_BUTTON = "فتح"
PIN_NOT_CONFIGURED = (
    "لم يتم تكوين رمز PIN. يفتح التطبيق بدون حماية.\n"
    "لتعيين واحد: python scripts/set_pin.py <PIN>"
)

# --- تأكيد الرمز السري (نافذة قابلة لإعادة الاستخدام)
PIN_CONFIRM_TITLE = "التأكيد مطلوب"
PIN_CONFIRM_PROMPT = "أدخل الرمز السري للتأكيد."
PIN_CONFIRM_WRONG = "الرمز السري غير صحيح."
PIN_CONFIRM_BUTTON = "تأكيد"

# --- الأدوار والجلسة
ROLE_LABELS = {
    "cashier": "أمين صندوق",
    "manager": "مدير",
    "owner": "المالك",
}
LOGIN_GREETING = "مرحبًا، {name}"

# ======================================================================
# 5. الجولة الإرشادية
# ======================================================================

FEATURE_TOUR_TITLE = "استكشاف التطبيق"
FEATURE_TOUR_WELCOME = "مرحبًا بك في إدارة المخزون ونقاط البيع!"
FEATURE_TOUR_CHECKOUT_TITLE = "نقطة البيع (الكاشير)"
FEATURE_TOUR_CHECKOUT_DESC = (
    "أنجز مبيعاتك بسرعة. ابحث باستخدام الباركود أو الاسم، "
    "وطبق الخصومات، وقم بالتحصيل نقدًا أو بالبطاقة."
)
FEATURE_TOUR_INVENTORY_TITLE = "المخزون"
FEATURE_TOUR_INVENTORY_DESC = (
    "أدر منتجاتك، وأسعار الجملة والتجزئة، وراقب مستويات المخزون."
)
FEATURE_TOUR_STATS_TITLE = "الإحصائيات والتقارير"
FEATURE_TOUR_STATS_DESC = (
    "تتبع إيراداتك، وأفضل المبيعات، وصدر التقارير (PDF، Excel) لمحاسبتك."
)
FEATURE_TOUR_ALERTS_TITLE = "التنبيهات والديون"
FEATURE_TOUR_ALERTS_DESC = (
    "احصل على إشعارات بانخفاض المخزون وتتبع ديون العملاء قيد الانتظار."
)
FEATURE_TOUR_PRINT_TITLE = "الطباعة والملصقات"
FEATURE_TOUR_PRINT_DESC = (
    "اطبع إيصالات الدفع على طابعتك الحرارية (ESC/POS) وأنشئ ملصقات الباركود لأصنافك."
)

# --- جولة إرشادية تفاعلية
FEATURE_TOUR_WELCOME_DESC = (
    "لنقم بجولة سريعة وتفاعلية في التطبيق. سنتنقل بين الشاشات معًا."
)
FEATURE_TOUR_NAV_CAISSE_DESC = (
    "شاشة البيع. من هنا تمسح الباركود وتضيف إلى السلة وتُحصّل يوميًا."
)
FEATURE_TOUR_SEARCH_TITLE = "إضافة المنتجات"
FEATURE_TOUR_SEARCH_DESC = (
    "امسح الباركود أو اكتب الاسم، ثم اضغط Entrée لإضافة الصنف إلى السلة."
)
FEATURE_TOUR_PAY_TITLE = "التحصيل (F12)"
FEATURE_TOUR_PAY_DESC = (
    "أنهِ البيع: دفع كامل، أو جزئي (دَيْن) مرتبط بعميل. المفتاح F12 يفتح نافذة التحصيل."
)
FEATURE_TOUR_CUSTOMERS_TITLE = "العملاء"
FEATURE_TOUR_CUSTOMERS_DESC = "أدر ملف عملائك ومشترياتهم وديونهم الجارية."
FEATURE_TOUR_SETTINGS_TITLE = "الإعدادات"
FEATURE_TOUR_SETTINGS_DESC = (
    "خصّص الإيصال والطابعة واللغة ولون التمييز، واحفظ نسخة من بياناتك."
)
FEATURE_TOUR_DONE_TITLE = "أنت جاهز!"
FEATURE_TOUR_DONE_DESC = (
    "هذا كل شيء! يمكنك إعادة تشغيل الجولة في أي وقت من الإعدادات. بيعًا موفقًا."
)
FEATURE_TOUR_NEXT = "التالي"
FEATURE_TOUR_PREV = "السابق"
FEATURE_TOUR_SKIP = "تخطٍّ"
FEATURE_TOUR_FINISH = "إنهاء"
FEATURE_TOUR_STEP = "خطوة {n}/{total}"

# ======================================================================
# 6. شريط العنوان
# ======================================================================

TITLEBAR_MINIMIZE = "تصغير"
TITLEBAR_MAXIMIZE = "تكبير"
TITLEBAR_RESTORE = "استعادة"
TITLEBAR_FULLSCREEN = "ملء الشاشة (F11)"
TITLEBAR_EXIT_FULLSCREEN = "الخروج من ملء الشاشة (F11)"
TITLEBAR_CLOSE = "إغلاق"

# ======================================================================
# 7. التنقل
# ======================================================================

NAV_SECTION = "القائمة"
NAV_CHECKOUT = "نقطة البيع"
NAV_INVENTORY = "المخزون"
NAV_CUSTOMERS = "العملاء"
NAV_SALES = "المبيعات"
NAV_PURCHASES = "المشتريات والموردون"
NAV_CREANCES = "الديون"
NAV_STATISTICS = "الإحصائيات"
NAV_DASHBOARD = "لوحة التحكم"
NAV_ALERTS = "التنبيهات"
NAV_LABELS = "الملصقات"
NAV_SUPPLIERS = "الموردون"
NAV_SETTINGS = "الإعدادات"

# ======================================================================
# 8. مستويات الأسعار والتعبئة
# ======================================================================

PRICE_DETAIL = "تجزئة"
PRICE_GROS = "جملة"
PRICE_SUPER_GROS = "جملة الجملة"
PRICE_LEVEL_LABELS = {
    "detail": PRICE_DETAIL,
    "gros": PRICE_GROS,
    "super_gros": PRICE_SUPER_GROS,
}
PRICE_LEVEL_MANUAL = "يدوي"
CHECKOUT_MANUAL_PRICE_TIP = "تم إدخال السعر يدويًا (أعلى من الحد الأدنى)."

PACKAGING_UNIT = "وحدة"
CHECKOUT_COL_PACKAGING = "التعبئة"
PRODUCT_PACKAGINGS = "التعبئة (اختياري)"
PACKAGING_ADD = "إضافة تعبئة"
PACKAGING_LABEL = "الاسم (مثل كرتونة)"
PACKAGING_LABEL_COL = "الاسم"
PACKAGING_UNITS_COL = "الوحدات/العبوة"
PACKAGING_UNIT_COUNT = "الوحدات في العبوة"
PACKAGING_REMOVE = "إزالة"
PACKAGING_HINT = "لكل تعبئة سعرها الخاص وتستهلك عدد معين من وحدات المخزون."
CHECKOUT_BASE_UNITS = "{n} وحدات"

# ======================================================================
# 9. نقطة البيع
# ======================================================================

CHECKOUT_TITLE = "نقطة البيع"
CHECKOUT_SEARCH_PLACEHOLDER = "امسح الباركود أو اكتب اسمًا… (اضغط Enter للإضافة)"
CHECKOUT_CART_EMPTY = "السلة فارغة"
CHECKOUT_CART_EMPTY_HINT = "امسح الباركود أو ابحث عن منتج."
CHECKOUT_PAY = "دفع  (F12)"
CHECKOUT_TOTAL = "الإجمالي"
CHECKOUT_COL_PRODUCT = "المنتج"
CHECKOUT_COL_LEVEL = "مستوى السعر"
CHECKOUT_COL_UNIT_PRICE = "سعر الوحدة"
CHECKOUT_COL_QTY = "الكمية"
CHECKOUT_COL_TOTAL = "إجمالي السطر"
CHECKOUT_COL_REMOVE = ""
CHECKOUT_COL_DISCOUNT = "الخصم"
CHECKOUT_REMOVE_LINE = "إزالة السطر"
CHECKOUT_DISCOUNT_TIP = "تم تطبيق الخصم على السطر (تم اعتماده بواسطة الخادم)."
CHECKOUT_DONE_TOAST = "تم تسجيل البيع — جاري طباعة الإيصال…"
CHECKOUT_NO_RESULT = "لم يتم العثور على منتج لـ «{query}»."
CHECKOUT_STOCK_BADGE = "المخزون {count}"
CHECKOUT_OUT_OF_STOCK = "نفد من المخزون"
CHECKOUT_CUSTOMER_LABEL = "العميل:"
CHECKOUT_CUSTOMER_ANONYMOUS = "مجهول"
CHECKOUT_CUSTOMER_CLEAR = "إزالة العميل"
RECEIPT_PRINT_FAILED = "فشل الطباعة: {path}"

# --- تعليق الفاتورة (تعليق / استئناف)
CHECKOUT_SUSPEND = "تعليق"
CHECKOUT_RESUME = "استئناف"
CHECKOUT_SUSPEND_TIP = "تعليق الفاتورة الحالية (F9)"
CHECKOUT_RESUME_TIP = "استئناف فاتورة معلّقة (F10)"
CHECKOUT_SUSPEND_EMPTY = "السلة فارغة — لا شيء لتعليقه"
CHECKOUT_SUSPENDED_TOAST = "تم تعليق الفاتورة"
CHECKOUT_RESUME_CONFIRM = "سيتم تعليق السلة الحالية قبل الاستدعاء. هل تريد المتابعة؟"
CHECKOUT_PARKED_ENTRY = "{time} — {count} أصناف — الزبون: {customer}"

# --- رصيد الزبون والسعر المعتاد
CHECKOUT_BALANCE_WARNING = "⚠ رصيد غير مسدد: {balance}"
CHECKOUT_PRICE_LEVEL_APPLIED = "تم تطبيق سعر {level} (زبون معتاد)"

# --- رمز العرض
CHECKOUT_PROMO_LABEL = "رمز العرض:"
CHECKOUT_PROMO_PLACEHOLDER = "الرمز…"
CHECKOUT_PROMO_APPLY = "تطبيق"
CHECKOUT_PROMO_REMOVE = "إزالة رمز العرض"
CHECKOUT_PROMO_APPLIED = "الرمز {code}: -{discount}"
CHECKOUT_PROMO_EMPTY_CART = "أضف أصنافًا إلى السلة أولاً."

# ======================================================================
# 10. الدفع
# ======================================================================

PAYMENT_TITLE = "التحصيل"
PAYMENT_TOTAL_LABEL = "إجمالي الدفع"
PAYMENT_FULL = "دفع كامل"
PAYMENT_FULL_HINT = "تحصيل كامل المبلغ الآن"
PAYMENT_PARTIAL = "دفع جزئي (دين/ائتمان)"
PAYMENT_PARTIAL_HINT = "تحصيل جزء من المبلغ، والباقي دَيْن على العميل"
PAYMENT_CLIENT_SECTION = "العميل (إلزامي للبيع بالدَّيْن)"
PAYMENT_AMOUNT_LABEL = "المبلغ المدفوع الآن"
PAYMENT_REMAINING_LABEL = "المبلغ المتبقي"
PAYMENT_CUSTOMER_REQUIRED = "يجب ربط الدفع الجزئي بعميل (الاسم ورقم الهاتف)."
PAYMENT_CONFIRM = "دفع"
PAYMENT_CHANGE_CUSTOMER = "تغيير"
PAYMENT_RECORD_TITLE = "تسجيل دفعة"
PAYMENT_RECORD_BALANCE = "الرصيد المتبقي: {balance}"
PAYMENT_RECORD_DONE = "تم تسجيل دفعة بقيمة {amount}."
PAYMENT_AMOUNT_TOO_HIGH = "المبلغ يتجاوز الرصيد المتبقي."
PAYMENT_AMOUNT_REQUIRED = "أدخل مبلغًا أكبر من الصفر."

# --- دفع جزئي: إرفاق أو إنشاء عميل
PAYMENT_PARTIAL_NEED_CUSTOMER = PAYMENT_CUSTOMER_REQUIRED
PAYMENT_NEW_CUSTOMER_NAME = "اسم العميل"
PAYMENT_NEW_CUSTOMER_PHONE = "الهاتف"
PAYMENT_ATTACH_EXISTING = "عميل حالي"
PAYMENT_CREATE_NEW = "عميل جديد"

# --- طريقة الدفع
PAYMENT_METHOD_LABEL = "طريقة الدفع"
PAYMENT_METHOD_CASH = "نقدًا"
PAYMENT_METHOD_CARD = "بطاقة"
PAYMENT_METHOD_MOBILE = "موبايل"
PAYMENT_METHOD_OTHER = "أخرى"
PAYMENT_METHOD_LABELS = {
    "cash": PAYMENT_METHOD_CASH,
    "card": PAYMENT_METHOD_CARD,
    "mobile": PAYMENT_METHOD_MOBILE,
    "other": PAYMENT_METHOD_OTHER,
}

# ======================================================================
# 11. إغلاق الصندوق
# ======================================================================

CHECKOUT_CLOSE_DAY = "إغلاق الصندوق"
CHECKOUT_CLOSE_DONE = "تم الإغلاق"
CLOSING_TITLE = "إغلاق الصندوق"
CLOSING_SECTION_SUMMARY = "ملخص تلقائي"
CLOSING_SECTION_COUNT = "العد الفعلي"
CLOSING_SECTION_ACTIONS = "إجراءات"
CLOSING_SALES_COUNT = "مبيعات اليوم"
CLOSING_REVENUE = "رقم المبيعات"
CLOSING_CASH = "نقدا"
CLOSING_CARD = "بطاقة"
CLOSING_TRANSFER = "تحويل"
CLOSING_DISCOUNTS = "الخصومات الممنوحة"
CLOSING_REFUNDS = "المبالغ المرجعة"
CLOSING_EXPECTED_CASH = "النقد المتوقع في الصندوق"
CLOSING_PHYSICAL_LABEL = "النقد المحصى في الصندوق (دج)"
CLOSING_GAP_LABEL = "فرق الصندوق:"
CLOSING_GAP_POS = "+{amount}"
CLOSING_GAP_NEG = "-{amount}"
CLOSING_NOTE_LABEL = "ملاحظة عن الفرق (اختياري)"
CLOSING_NOTE_PLACEHOLDER = "تفسير أي فرق محتمل…"
CLOSING_PRINT = "طباعة تقرير الإغلاق"
CLOSING_CONFIRM = "تأكيد الإغلاق"
CLOSING_DONE_TOAST = "تم تسجيل إغلاق الصندوق."
CLOSING_NO_SALES = "لا توجد مبيعات اليوم — لا شيء لإغلاقه."
CLOSING_PIN_PROMPT = "أدخل الرمز السري لإغلاق الصندوق."

# ======================================================================
# 12. العملاء
# ======================================================================

CUSTOMERS_TITLE = "العملاء"
CUSTOMERS_SEARCH_PLACEHOLDER = "البحث بالاسم أو الهاتف…"
CUSTOMERS_NEW = "عميل جديد"
CUSTOMERS_EMPTY = "لا يوجد عملاء مسجلين"
CUSTOMERS_EMPTY_HINT = "أنشئ عميلاً لتتبع مشترياته وديونه."
CUSTOMER_DIALOG_NEW = "عميل جديد"
CUSTOMER_DIALOG_EDIT = "تعديل العميل"
CUSTOMER_NAME = "الاسم الكامل"
CUSTOMER_PHONE = "الهاتف"
CUSTOMER_NOTE = "ملاحظة (اختياري)"
CUSTOMER_STAT_REVENUE = "الإيرادات"
CUSTOMER_STAT_PROFIT = "الأرباح"
CUSTOMER_STAT_SALES = "المبيعات"
CUSTOMER_STAT_BALANCE = "الديون الحالية"
CUSTOMER_STAT_LAST = "آخر شراء"
CUSTOMER_NEVER_PURCHASED = "أبدًا"
CUSTOMER_SALES_HISTORY = "سجل المبيعات"
CUSTOMER_SALE_PAID = "مدفوعة"
CUSTOMER_SALE_CREDIT = "دين"
CUSTOMER_RECORD_PAYMENT = "تسجيل دفعة"
CUSTOMER_TOP_TITLE = "أفضل العملاء"
CUSTOMER_TOP_HINT = "الترتيب حسب الإيرادات — حدد عميلاً للتفاصيل."
CUSTOMER_COL_DATE = "التاريخ"
CUSTOMER_COL_TOTAL = "الإجمالي"
CUSTOMER_COL_PAID = "المدفوع"
CUSTOMER_COL_BALANCE = "المتبقي"
CUSTOMER_COL_STATUS = "الحالة"

# --- أداة البحث عن العملاء (CustomerSearchBox)
CUSTOMER_SEARCH_PLACEHOLDER = "البحث عن عميل (الاسم أو الهاتف)…"
CUSTOMER_SEARCH_NO_RESULT = "لم يتم العثور على عملاء."
CUSTOMER_SEARCH_CREATE = "إنشاء «{query}»…"
CUSTOMER_ATTACH = "إرفاق"
CUSTOMER_DETACH = "إزالة العميل"
CUSTOMER_ANONYMOUS = "مجهول"

# --- السعر المعتاد (مستوى السعر الافتراضي)
CUSTOMER_DEFAULT_PRICE_LEVEL = "السعر المعتاد"
CUSTOMER_PRICE_LEVEL_NONE = "لا شيء (حسب اختيار الكاشير)"

# ======================================================================
# 13. سجل المبيعات
# ======================================================================

SALES_TITLE = "المبيعات"
SALES_FILTER_TODAY = "اليوم"
SALES_FILTER_WEEK = "7 أيام"
SALES_FILTER_MONTH = "30 يومًا"
SALES_FILTER_ALL = "الكل"
SALES_TYPE_ALL = "الكل"
SALES_TYPE_GUEST_PENDING = "مجهولة للحل"
SALES_TYPE_GUEST_CONFIRMED = "مجهولة مؤكدة"
SALES_TYPE_WITH_CUSTOMER = "مع عميل"
SALES_TYPE_CREDIT = "آجل (دين)"
SALES_COL_DATE = "التاريخ"
SALES_COL_CUSTOMER = "العميل"
SALES_COL_TOTAL = "الإجمالي"
SALES_COL_PAID = "المدفوع"
SALES_COL_BALANCE = "المتبقي"
SALES_COL_STATUS = "الحالة"
SALES_STATUS_PAID = "مدفوعة"
SALES_STATUS_CREDIT = "دين"
SALES_EMPTY = "لا توجد مبيعات في هذه الفترة."
SALES_GUEST_PENDING_BADGE = "للحل"
SALES_GUEST_CONFIRMED_BADGE = "مجهول"

# --- تفاصيل البيع (تعيين العميل)
SALE_DETAIL_TITLE = "تفاصيل البيع"
SALE_RESOLVE_SECTION = "عميل هذه العملية"
SALE_LEAVE_ANONYMOUS = "ترك كمجهول"
SALE_CREATE_CUSTOMER = "إنشاء عميل"
SALE_ATTACH_CUSTOMER = "إرفاق عميل حالي"
SALE_ASSIGNED_DONE = "تم إرفاق العميل بعملية البيع."
SALE_LEFT_ANONYMOUS_DONE = "تم تمييز البيع كمجهول."
SALE_ALREADY_HAS_CUSTOMER = "هذه العملية مرتبطة بعميل بالفعل."
SALE_REPRINT_RECEIPT = "إعادة طباعة الإيصال"

# ======================================================================
# 14. المرتجعات (الاستردادات)
# ======================================================================

REFUND_BUTTON = "إنشاء إرجاع"
REFUND_DIALOG_TITLE = "إرجاع جديد (استرداد)"
REFUND_REASON_LABEL = "السبب (اختياري)"
REFUND_REASON_PLACEHOLDER = "إرجاع منتج، عيب، خطأ…"
REFUND_COL_PRODUCT = "المنتج"
REFUND_COL_AVAILABLE = "المتاح"
REFUND_COL_QTY = "الكمية المرتجعة"
REFUND_COL_PRICE = "سعر الوحدة"
REFUND_COL_TOTAL = "المجموع الفرعي"
REFUND_TOTAL = "إجمالي الإرجاع: {amount}"
REFUND_CONFIRM = "تأكيد الإرجاع"
REFUND_CREATED = "تم إنشاء الإرجاع بنجاح ({amount})."
REFUND_BADGE = "مرتجع"
REFUND_PRINT_RECEIPT = "طباعة وصل الإرجاع"
REFUND_HISTORY_TITLE = "المرتجعات المصدرة"
REFUND_EMPTY = "لا يوجد عناصر قابلة للإرجاع."

# ======================================================================
# 15. المخزون والجرد
# ======================================================================

INVENTORY_TITLE = "المخزون"
INVENTORY_NEW_PRODUCT = "منتج جديد"
INVENTORY_EDIT_PRODUCT = "تعديل"
INVENTORY_ARCHIVE_PRODUCT = "أرشفة"
INVENTORY_ALL_CATEGORIES = "جميع الفئات"
INVENTORY_ALL_PRODUCTS = "جميع المنتجات"
INVENTORY_CATEGORIES = "الفئات"
INVENTORY_UNCATEGORIZED = "بدون فئة"
INVENTORY_COL_NAME = "المنتج"
INVENTORY_COL_BARCODE = "الباركود"
INVENTORY_COL_CATEGORY = "الفئة"
INVENTORY_COL_STOCK = "المخزون"
INVENTORY_COL_DETAIL = "تجزئة"
INVENTORY_COL_GROS = "جملة"
INVENTORY_COL_SUPER_GROS = "جملة الجملة"
INVENTORY_COL_ACTIVE = "نشط"
INVENTORY_ARCHIVE_CONFIRM = (
    "هل تريد أرشفة المنتج «{name}»؟\n" "لن يكون قابلاً للبيع ولكنه سيبقى في السجل."
)
INVENTORY_SELECT_ROW_FIRST = "يرجى تحديد منتج من القائمة أولاً."
INVENTORY_LOW_STOCK_BADGE = "مخزون منخفض"
INVENTORY_EMPTY = "لا يوجد منتجات في المخزون"
INVENTORY_EMPTY_HINT = "أنشئ منتجك الأول للبدء في البيع."
INVENTORY_DETAIL_HINT = "نقر مزدوج على المنتج: عرض التفاصيل والإحصائيات."
INVENTORY_TAB_PRODUCTS = "المنتجات"
INVENTORY_TAB_MOVEMENTS = "حركات المخزون"
INVENTORY_ADJUST_BUTTON = "تعديل الجرد"
INVENTORY_LABELS_BUTTON = "طباعة الملصقات"

# ======================================================================
# 16. بطاقة المنتج
# ======================================================================

# --- النموذج
PRODUCT_DIALOG_NEW = "منتج جديد"
PRODUCT_DIALOG_EDIT = "تعديل المنتج"
PRODUCT_NAME = "اسم المنتج"
PRODUCT_BARCODE = "الباركود (اختياري)"
PRODUCT_CATEGORY = "الفئة"
PRODUCT_NO_CATEGORY = "بدون فئة"
PRODUCT_NEW_CATEGORY = "فئة جديدة…"
PRODUCT_NEW_CATEGORY_PROMPT = "اسم الفئة الجديدة:"
PRODUCT_COST_PRICE = "سعر الشراء"
PRODUCT_PRICE_DETAIL = "سعر التجزئة"
PRODUCT_PRICE_GROS = "سعر الجملة"
PRODUCT_PRICE_SUPER_GROS = "سعر جملة الجملة (الحد الأدنى)"
PRODUCT_PRICE_ORDER_HINT = "الترتيب المطلوب: تجزئة ≥ جملة ≥ جملة الجملة."
PRODUCT_PRICE_ORDER_ERROR = (
    "أسعار غير متناسقة: يجب أن يكون سعر التجزئة ≥ سعر الجملة، "
    "والذي بدوره يجب أن يكون ≥ سعر جملة الجملة."
)
PRODUCT_STOCK = "الكمية في المخزون"
PRODUCT_LOW_STOCK_THRESHOLD = "حد تنبيه المخزون"
PRODUCT_ACTIVE = "منتج نشط (قابل للبيع)"
PRODUCT_IMAGE = "صورة المنتج"
PRODUCT_IMAGE_CHOOSE = "اختيار صورة…"
PRODUCT_IMAGE_REMOVE = "إزالة الصورة"
PRODUCT_PRINT_LABEL = "طباعة الملصق"
PRODUCT_IMAGE_FILTER = "الصور (*.jpg *.jpeg *.png *.webp)"
PRODUCT_IMAGE_UPLOAD_FAILED = "تم حفظ المنتج ولكن تعذر إرسال الصورة: {reason}"
PRODUCT_SAVED_TOAST = "تم حفظ المنتج «{name}»."

# --- التفاصيل والإحصائيات
PRODUCT_DETAIL_TITLE = "تفاصيل المنتج"
PRODUCT_DETAIL_STATS = "مبيعات المنتج"
PRODUCT_DETAIL_HISTORY = "سجل الحركات"
PRODUCT_TAB_INFO = "المعلومات"
PRODUCT_TAB_HISTORY = "السجل"
MOVEMENT_COL_DATE = "التاريخ"
MOVEMENT_COL_TYPE = "النوع"
MOVEMENT_COL_DELTA = "الكمية"
MOVEMENT_COL_AFTER = "بعد"
MOVEMENT_COL_REF = "المرجع"
MOVEMENT_TYPE_SALE = "بيع"
MOVEMENT_TYPE_PURCHASE = "شراء"
MOVEMENT_TYPE_REFUND = "استرداد"
MOVEMENT_TYPE_ADJUSTMENT = "تعديل"
MOVEMENT_EMPTY = "لا توجد حركات مسجلة لهذا المنتج."
MOVEMENT_STOCK_AFTER = "المخزون: {qty} و."
MOVEMENT_LOAD_MORE = "عرض المزيد"
PRODUCT_STAT_UNITS = "الوحدات المباعة"
PRODUCT_STAT_REVENUE = "الإيرادات"
PRODUCT_STAT_PROFIT = "الأرباح"
PERIOD_TODAY = "اليوم"
PERIOD_7_DAYS = "7 أيام"
PERIOD_30_DAYS = "30 يومًا"
PERIOD_365_DAYS = "365 يومًا"
PERIOD_ALL_TIME = "الإجمالي"
PERIOD_LABELS = {
    "today": PERIOD_TODAY,
    "last_7_days": PERIOD_7_DAYS,
    "last_30_days": PERIOD_30_DAYS,
    "last_365_days": PERIOD_365_DAYS,
    "all_time": PERIOD_ALL_TIME,
}

# ======================================================================
# 17. حركات المخزون والتعديل
# ======================================================================

# --- سجل الحركات
MOVEMENTS_COL_DATETIME = "التاريخ / الساعة"
MOVEMENTS_COL_PRODUCT = "المنتج"
MOVEMENTS_COL_CATEGORY = "الفئة"
MOVEMENTS_COL_TYPE = "النوع"
MOVEMENTS_COL_DELTA = "الكمية"
MOVEMENTS_COL_AFTER = "المخزون بعد"
MOVEMENTS_COL_REFERENCE = "المرجع"
MOVEMENTS_COL_NOTE = "ملاحظة"
MOVEMENTS_SEARCH_PLACEHOLDER = "تصفية حسب المنتج…"
MOVEMENTS_FILTER_ALL_TYPES = "كل الأنواع"
MOVEMENTS_FILTER_SALES = "المبيعات"
MOVEMENTS_FILTER_PURCHASES = "المشتريات"
MOVEMENTS_FILTER_ADJUSTMENTS = "التعديلات"
MOVEMENTS_FILTER_RETURNS = "المرتجعات"
MOVEMENTS_FILTER_ALL_CATEGORIES = "كل الفئات"
MOVEMENTS_FROM = "من"
MOVEMENTS_TO = "إلى"
MOVEMENTS_EXPORT_XLSX = "تصدير Excel"
MOVEMENTS_EXPORT_EMPTY = "لا توجد حركات للتصدير."
MOVEMENTS_EMPTY = "لا توجد حركات مخزون في هذه الفترة."
MOVEMENTS_LOAD_MORE = "عرض المزيد"

# --- تعديل الجرد
ADJUST_TITLE = "تعديل الجرد"
ADJUST_STEP_PRODUCT = "1. اختيار المنتج"
ADJUST_STEP_ENTRY = "2. إدخال المخزون المحصى"
ADJUST_STEP_CONFIRM = "3. التأكيد"
ADJUST_SEARCH_PLACEHOLDER = "ابحث عن منتج لتعديله…"
ADJUST_CURRENT_STOCK = "المخزون الحالي: {qty} وحدة"
ADJUST_COUNTED_LABEL = "المخزون الفعلي المحصى:"
ADJUST_DELTA_POS = "+{n} وحدة"
ADJUST_DELTA_NEG = "-{n} وحدة"
ADJUST_DELTA_ZERO = "لا تغيير"
ADJUST_REASON_LABEL = "السبب:"
ADJUST_NOTE_LABEL = "ملاحظة (اختياري):"
ADJUST_NOTE_PLACEHOLDER = "تعليق…"
ADJUST_NEXT = "التالي"
ADJUST_BACK = "رجوع"
ADJUST_CONFIRM_BUTTON = "تأكيد التعديل"
ADJUST_CONFIRM_SENTENCE = (
    "سيتم تعديل مخزون « {product} » من {old} إلى {new} (الفرق: {delta})."
)
ADJUST_DONE_TOAST = "تم تحديث مخزون {product}: {old} ← {new} وحدة"
ADJUST_SELECT_PRODUCT_FIRST = "اختر منتجًا أولاً."
ADJUST_REASONS = {
    "inventaire": "جرد فعلي",
    "perte": "خسارة",
    "casse": "كسر",
    "correction": "تصحيح",
    "autre": "أخرى",
}

# ======================================================================
# 18. الموردون والمشتريات
# ======================================================================

# --- قائمة الموردين
SUPPLIERS_TITLE = "الموردون"
SUPPLIERS_SEARCH_PLACEHOLDER = "البحث بالاسم أو الهاتف…"
SUPPLIERS_NEW = "مورد جديد"
SUPPLIERS_EMPTY = "لا يوجد موردون مسجلون"
SUPPLIERS_EMPTY_HINT = "أضف موردًا لإدارة مشترياتك."
SUPPLIER_DIALOG_NEW = "مورد جديد"
SUPPLIER_DIALOG_EDIT = "تعديل المورد"
SUPPLIER_NAME = "الاسم"
SUPPLIER_PHONE = "الهاتف"
SUPPLIER_NOTE = "ملاحظة (اختياري)"
SUPPLIER_TAB_INFO = "المعلومات"
SUPPLIER_TAB_ORDERS = "سندات الاستلام"
SUPPLIER_STAT_ORDERS = "الطلبات"
SUPPLIER_STAT_TOTAL = "إجمالي المشتريات"
SUPPLIER_STAT_BALANCE = "الديون الحالية"
SUPPLIER_STAT_PURCHASED = "إجمالي المشتريات"
SUPPLIER_STAT_PAID = "إجمالي المدفوع"
SUPPLIER_STAT_DUE = "المتبقي"
SUPPLIER_ORDERS_HISTORY = "سجل الطلبات"
SUPPLIER_COL_DATE = "التاريخ"
SUPPLIER_COL_TOTAL = "الإجمالي"
SUPPLIER_COL_PAID = "المدفوع"
SUPPLIER_COL_BALANCE = "المتبقي"
SUPPLIER_COL_STATUS = "الحالة"
SUPPLIER_SAVED_TOAST = "تم تسجيل المورد."
SUPPLIER_ARCHIVE_CONFIRM = (
    "هل تريد أرشفة المورد «{name}»؟\n"
    "ستتم إزالته من القائمة ولكن سيتم الاحتفاظ بالسجل."
)

# --- شاشة المشتريات والموردون (التبويبات)
PURCHASES_TAB_SUPPLIERS = "الموردون"
PURCHASES_TAB_ORDERS = "سندات الاستلام"

# --- سندات الاستلام (النموذج البسيط)
PO_DIALOG_TITLE = "استلام المخزون"
PO_SUPPLIER_LABEL = "المورد"
PO_ADD_LINE = "إضافة منتج"
PO_COL_PRODUCT = "المنتج"
PO_COL_QTY = "الكمية"
PO_COL_UNIT_COST = "تكلفة الوحدة"
PO_COL_TOTAL = "إجمالي السطر"
PO_COL_REMOVE = ""
PO_TOTAL = "الإجمالي"
PO_PAYMENT_NOW = "الدفع الآن (اختياري)"
PO_CONFIRM = "استلام"
PO_DONE_TOAST = "تم استلام المخزون بنجاح."
PO_RECORD_PAYMENT = "تسجيل دفعة"

# --- العرض الشامل لسندات الاستلام (المرشّحات)
PO_FILTER_SUPPLIER = "المورّد"
PO_FILTER_ALL_SUPPLIERS = "كل الموردين"
PO_FILTER_STATUS = "الحالة"
PO_STATUS_ALL = "الكل"
PO_STATUS_PAID = "مدفوع"
PO_STATUS_PARTIAL = "جزئي"
PO_STATUS_UNPAID = "غير مدفوع"
PO_FILTER_FROM = "من"
PO_FILTER_TO = "إلى"
PO_FILTER_APPLY = "تصفية"

# --- العرض الشامل لسندات الاستلام (الجدول)
PO_GCOL_DATE = "التاريخ"
PO_GCOL_SUPPLIER = "المورّد"
PO_GCOL_REF = "المرجع"
PO_GCOL_TOTAL = "الإجمالي"
PO_GCOL_PAID = "المدفوع"
PO_GCOL_BALANCE = "المتبقي"
PO_GCOL_STATUS = "الحالة"
PO_GCOL_ACTIONS = "إجراءات"
PO_NEW_ORDER = "سند جديد"
PO_ACTION_PAYMENT = "دفعة"
PO_ACTION_DETAILS = "تفاصيل"
PO_ORDERS_EMPTY = "لا توجد سندات استلام"
PO_ORDERS_EMPTY_HINT = "أنشئ سنداً لاستلام المخزون."
PO_UNKNOWN_SUPPLIER = "مورّد غير معروف"

# --- نافذة سند الاستلام (إنشاء / تفاصيل)
PO_DIALOG_NEW = "سند استلام جديد"
PO_DIALOG_DETAILS = "تفاصيل السند"
PO_LINES_SECTION = "سطور الطلب"
PO_LINE_PRODUCT_PLACEHOLDER = "ابحث عن منتج…"
PO_ADD_LINE_ROW = "إضافة سطر"
PO_SUBMIT_UPDATE_STOCK = "تأكيد وتحديث المخزون"
PO_CREATED_TOAST = "تم إنشاء السند — تم تحديث المخزون."
PO_SELECT_SUPPLIER = "اختر مورّداً."
PO_NEED_ONE_LINE = "أضف سطراً واحداً على الأقل بمنتج وتكلفة."

# ======================================================================
# 19. الإحصائيات ولوحة التحكم والمقارنة
# ======================================================================

STATISTICS_TITLE = "الإحصائيات"
STATS_EXPORT_PDF = "تصدير PDF"
STATS_EXPORT_XLSX = "تصدير Excel"
STATS_TAB_DASHBOARD = "لوحة المعلومات"
STATS_TAB_COMPARISON = "مقارنة الفترات"
STATS_PIN_REQUIRED = "الإحصائيات تتطلب رمز PIN الخاص بالمالك."

# --- نظرة عامة
STATS_THIS_WEEK = "هذا الأسبوع"
STATS_THIS_MONTH = "هذا الشهر"
STATS_THIS_YEAR = "هذا العام"
STATS_OVERVIEW_LABELS = {
    "today": PERIOD_TODAY,
    "this_week": STATS_THIS_WEEK,
    "this_month": STATS_THIS_MONTH,
    "this_year": STATS_THIS_YEAR,
}
STATS_REVENUE = "الإيرادات"
STATS_PROFIT = "إجمالي الأرباح"
STATS_SALES_COUNT = "المبيعات"
STATS_SUBTITLE = "نظرة عامة على نشاطك"
STATS_AVG_BASKET = "متوسط السلة"
STATS_MARGIN = "الهامش"
STATS_OF_REVENUE = "من الإيرادات"
STATS_EVOLUTION = "التطور حسب الفترة"
STATS_PERIOD_SUB = "الربح {profit} · {count} مبيعات"
STATS_NO_DATA = "لا توجد بيانات في هذه الفترة"
STATS_PRESET_TODAY = "اليوم"
STATS_PRESET_7D = "7 أيام"
STATS_PRESET_30D = "30 يومًا"
STATS_VS_PREVIOUS = "مقارنة بالفترة السابقة"
STATS_FROM = "من"
STATS_TO = "إلى"
STATS_DISCOUNTS = "الخصومات الممنوحة"

# --- أفضل المبيعات
STATS_TOP_PRODUCTS = "أفضل المبيعات"
STATS_COL_PRODUCT = "المنتج"
STATS_COL_QTY = "الكمية المباعة"
STATS_COL_REVENUE = "الإيرادات"
STATS_SORT_QTY = "الكمية"
STATS_SORT_PROFIT = "الربح"
STATS_COL_MARGIN = "الهامش"

# --- الارتباطات (market-basket)
STATS_ASSOCIATIONS = "منتجات تُشترى معًا غالبًا"
STATS_ASSOCIATION_RULE = "العملاء الذين يشترون {antecedent} يأخذون أيضًا {consequent}"
STATS_ASSOCIATION_DETAIL = "الثقة {confidence} % · الدعم {support} % · الرفع {lift}"
STATS_ASSOCIATIONS_EMPTY = "لا يوجد مبيعات كافية لاكتشاف الارتباطات بعد"
STATS_ASSOCIATIONS_EMPTY_HINT = (
    "تظهر الارتباطات عندما يتم شراء المنتجات معًا " "في العديد من المبيعات خلال الفترة."
)

# --- طرق الدفع
STATS_PAYMENT_METHODS = "التوزيع حسب طريقة الدفع"
STATS_PM_COL_METHOD = "الطريقة"
STATS_PM_COL_TOTAL = "المبلغ"
STATS_PM_COL_COUNT = "المعاملات"

# --- التقرير اليومي
STATS_DAILY_REPORT = "التقرير اليومي"
STATS_DAILY_REPORT_TITLE = "التقرير اليومي"
STATS_DAILY_REPORT_PROMPT = "اختر تاريخ التقرير:"
STATS_DAILY_REPORT_GENERATE = "إنشاء التقرير"

# --- الرسوم البيانية والاتجاهات
STATS_TREND_TITLE = "تطور الإيرادات والأرباح"
STATS_CHART_EMPTY = "لا توجد بيانات لعرضها في هذه الفترة"
STATS_REVENUE_LEGEND = "الإيرادات"
STATS_PROFIT_LEGEND = "الأرباح"
STATS_DONUT_TOTAL = "الإجمالي"
STATS_ITEMS_PER_SALE = "{value} عنصر / بيع"

# --- لمحة مالية ومخزون
STATS_STOCK_VALUE = "قيمة المخزون"
STATS_STOCK_VALUE_RETAIL = "قيمة البيع: {value}"
STATS_CUSTOMER_CREDIT = "ديون العملاء"
STATS_CREDIT_SALES = "{count} مبيعات غير مدفوعة"
STATS_SUPPLIER_DEBT = "ديون الموردين"
STATS_SUPPLIER_ORDERS = "{count} طلبات مفتوحة"
STATS_OUT_OF_STOCK = "منتجات نافدة"
STATS_LOW_STOCK_HINT = "+ {count} تحت عتبة التنبيه"

# --- الفئات
STATS_CATEGORY_TITLE = "المبيعات حسب الفئة"
STATS_CATEGORY_MARGIN_TITLE = "ربحية الفئات"
STATS_NO_CATEGORY = "بدون فئة"
STATS_OTHERS = "أخرى"

# --- الازدحام (ساعات / أيام)
STATS_BUSY_TITLE = "الازدحام"
STATS_BUSY_HOURS = "ساعات"
STATS_BUSY_DAYS = "أيام"
STATS_HOUR_LABEL = "{hour}س"
WEEKDAY_SHORT = ["إثنين", "ثلاثاء", "أربعاء", "خميس", "جمعة", "سبت", "أحد"]

# --- أفضل العملاء
STATS_TOP_CUSTOMERS = "أفضل العملاء"
STATS_COL_CUSTOMER = "العميل"
STATS_COL_PHONE = "الهاتف"
STATS_COL_PURCHASES = "المشتريات"
STATS_CUSTOMERS_EMPTY = "لا يوجد عملاء في هذه الفترة"
STATS_CUSTOMERS_SUB = "{active} نشط · {new} جديد"

# --- المخزون الراكد
STATS_DEAD_STOCK_TITLE = "المخزون الراكد"
STATS_DEAD_STOCK_EMPTY = "لا يوجد مخزون راكد في هذه المدة"
STATS_COL_STOCK = "المخزون"
STATS_COL_TIED = "رأس المال المجمّد"
STATS_COL_LAST_SALE = "آخر بيع"
STATS_DAYS_AGO = "{days} يوم"
STATS_NEVER_SOLD = "أبداً"
STATS_DEAD_30 = "30 ي"
STATS_DEAD_60 = "60 ي"
STATS_DEAD_90 = "90 ي"

# --- مقارنة الفترات
CMP_PERIOD_A = "الفترة أ"
CMP_PERIOD_B = "الفترة ب"
CMP_PRESET_MONTH = "الشهر مقابل السابق"
CMP_PRESET_QUARTER = "الفصل مقابل السابق"
CMP_PRESET_YEAR = "السنة مقابل السابقة"
CMP_COMPARE = "قارن"
CMP_TABLE_TITLE = "المقارنة"
CMP_CHART_TITLE = "رقم المبيعات حسب اليوم"
CMP_COL_METRIC = "المقياس"
CMP_COL_CHANGE = "التغير"
CMP_METRIC_REVENUE = "رقم المبيعات"
CMP_METRIC_PROFIT = "الربح"
CMP_METRIC_SALES = "عدد المبيعات"
CMP_METRIC_BASKET = "متوسط السلة"
CMP_METRIC_CUSTOMERS = "الزبائن"
CMP_METRIC_TOP_CATEGORY = "مبيعات أفضل فئة"

# --- لوحة التحكم (الصفحة الرئيسية)
DASHBOARD_TITLE = "لوحة التحكم"
DASH_TODAY_REVENUE = "رقم مبيعات اليوم"
DASH_TODAY_SALES = "مبيعات اليوم"
DASH_LOW_STOCK = "تنبيهات المخزون المنخفض"
DASH_OUTSTANDING = "الديون القائمة"
DASH_TREND_TITLE = "تطور آخر 7 أيام"
DASH_TOP_PRODUCTS = "أفضل 5 منتجات"
DASH_TOP_EMPTY = "لا مبيعات هذا الشهر"
DASH_FINANCIAL = "الوضع المالي"
DASH_CUSTOMER_CREDIT = "ديون الزبائن"
DASH_SUPPLIER_DEBT = "ديون الموردين"
DASH_RECENT_ACTIVITY = "النشاط الأخير"
DASH_NO_ACTIVITY = "لا مبيعات حديثة"
DASH_ANONYMOUS = "مجهول"

# ======================================================================
# 20. التنبيهات والديون
# ======================================================================

# --- التنبيهات
ALERTS_TITLE = "التنبيهات"
ALERTS_LOW_STOCK = "مخزون منخفض"
ALERTS_LOW_STOCK_EMPTY = "لا يوجد أي منتج تحت حد التنبيه"
ALERTS_LOW_STOCK_EMPTY_HINT = "كل المخزون أعلى من الحدود المكونة."
ALERTS_COL_PRODUCT = "المنتج"
ALERTS_COL_STOCK = "المخزون المتبقي"
ALERTS_COL_THRESHOLD = "الحد"
ALERTS_VIEW_PRODUCT = "عرض المنتج"
ALERTS_CREDITS = "ديون قيد الانتظار"
ALERTS_CREDITS_EMPTY = "لا توجد ديون قيد الانتظار"
ALERTS_CREDITS_EMPTY_HINT = "جميع المبيعات مدفوعة بالكامل."
ALERTS_AGE_DAYS = "{days} يوم"
ALERTS_AGE_TOOLTIP = (
    "عمر الدين: رمادي < 7 أيام، برتقالي 7–29 يومًا، " "أحمر ≥ 30 يومًا."
)
ALERTS_CREDIT_LINE = "الإجمالي {total} · المدفوع {paid}"
ALERTS_REMAINING = "المتبقي {balance}"
ALERTS_DEAD_STOCK_IN_STOCK = "في المخزون: {qty} و."
ALERTS_DEAD_STOCK_NOT_SOLD = "لم يُبَع منذ {days} يوماً"
ALERTS_DEAD_STOCK_NEVER = "لم يُبَع قط"
ALERTS_DEAD_STOCK_CREATE_PO = "إنشاء سند"
ALERTS_DEAD_STOCK_EMPTY = "لا يوجد مخزون راكد خلال {period} يوماً"
ALERTS_DEAD_STOCK_EMPTY_HINT = "المخزون يدور جيداً خلال هذه المدة."
ALERTS_NO_CATEGORY = "بدون فئة"

# --- ديون الزبائن
CREANCES_TITLE = "ديون الزبائن"
CREANCES_SUMMARY = "{total} مستحقة · {count} مدينون"
CREANCES_SEARCH = "ابحث عن زبون…"
CREANCES_COL_CUSTOMER = "الزبون"
CREANCES_COL_DATE = "تاريخ البيع"
CREANCES_COL_TOTAL = "الإجمالي"
CREANCES_COL_PAID = "المدفوع"
CREANCES_COL_BALANCE = "المتبقي"
CREANCES_COL_AGE = "قدم الدين"
CREANCES_COL_ACTIONS = "إجراءات"
CREANCES_ENCAISSER = "تحصيل"
CREANCES_RECEIPT = "إيصال"
CREANCES_AGE_DAYS = "{days} ي"
CREANCES_EMPTY = "لا توجد ديون قائمة"
CREANCES_EMPTY_HINT = "جميع المبيعات مسددة."
CREANCES_VIEW_FLAT = "قائمة"
CREANCES_VIEW_GROUPED = "حسب الزبون"
CREANCES_GROUP_SUBTOTAL = "المجموع الفرعي: {total}"
CREANCES_EXPORT_PDF = "تصدير PDF"
CREANCES_PAYMENT_DONE = "تم تسجيل الدفع."

# ======================================================================
# 21. الإعدادات
# ======================================================================

SETTINGS_TITLE = "الإعدادات"
SETTINGS_TAB_GENERAL = "عام"
SETTINGS_TAB_USERS = "المستخدمون"
SETTINGS_TAB_PROMOTIONS = "العروض"

# --- الإيصال
SETTINGS_RECEIPT_SECTION = "تخصيص الإيصال"
SETTINGS_SHOP_NAME = "اسم المتجر"
SETTINGS_PHONE = "الهاتف"
SETTINGS_ADDRESS = "العنوان"
SETTINGS_FOOTER = "رسالة التذييل"
SETTINGS_SHOW_CREDIT = "طباعة المدفوع / المتبقي في مبيعات الديون"
SETTINGS_PREVIEW_TITLE = "معاينة الإيصال"
SETTINGS_PREVIEW_SAMPLE_PRODUCT = "مثال لمنتج"
SETTINGS_PREVIEW_TOTAL = "الإجمالي"
SETTINGS_PREVIEW_PAID = "المدفوع"
SETTINGS_PREVIEW_REMAINING = "المبلغ المتبقي"
SETTINGS_PREVIEW_CUSTOMER = "العميل: علي بن علي"
SETTINGS_PREVIEW_DEFAULT_FOOTER = "شكرًا لزيارتكم!"
SETTINGS_PREVIEW_TICKET = "تذكرة رقم A1B2C3D4"

# --- اللغة
SETTINGS_LANGUAGE_SECTION = "اللغة"
SETTINGS_LANGUAGE_FR = "الفرنسية (Français)"
SETTINGS_LANGUAGE_AR = "العربية"
SETTINGS_RESTART_REQUIRED = (
    "تم تغيير لغة الواجهة. يرجى إعادة تشغيل التطبيق لتطبيق التغيير."
)

# --- الطباعة
SETTINGS_PRINTER_SECTION = "الطباعة"
SETTINGS_PRINTER_HINT = "اختيار الطابعة خاص بهذا الحاسوب."
SETTINGS_PRINTER_DEFAULT = "طابعة النظام الافتراضية"
SETTINGS_PRINTER_TEST = "صفحة اختبار"
SETTINGS_PRINTER_ESCPOS = "وضع حراري ESC/POS (درج النقود)"
SETTINGS_PRINTER_DRAWER = "فتح درج النقود"
SETTINGS_PRINTER_TEST_SENT = "تم إرسال صفحة الاختبار إلى الطابعة."

# --- المظهر والسمة
SETTINGS_APPEARANCE_SECTION = "المظهر"
SETTINGS_THEME_MODE = "الوضع"
SETTINGS_MODE_LIGHT = "فاتح"
SETTINGS_MODE_DARK = "داكن"
SETTINGS_ACCENT_SECTION = "لون التمييز"
SETTINGS_ACCENT_LABEL = "لون التمييز"
SETTINGS_ACCENT_CUSTOM = "مخصص…"
SETTINGS_CUSTOM_COLORS = "ألوان مخصصة (متقدم)"
SETTINGS_CUSTOM_HINT = (
    "اترك اللون الافتراضي ليتبع الوضع. الألوان المخصصة تُطبّق فوراً — معاينة حية."
)
SETTINGS_COLOR_BG = "الخلفية"
SETTINGS_COLOR_BG_DESC = "الخلفية العامة للشاشات"
SETTINGS_COLOR_SURFACE = "البطاقات / الأسطح"
SETTINGS_COLOR_SURFACE_DESC = "خلفية البطاقات والجداول والحقول"
SETTINGS_COLOR_TEXT = "النص"
SETTINGS_COLOR_TEXT_DESC = "اللون الأساسي للنص"
SETTINGS_COLOR_BORDER = "الحدود"
SETTINGS_COLOR_BORDER_DESC = "حدود الحقول والبطاقات"
SETTINGS_COLOR_RESET = "إعادة تعيين"
SETTINGS_COLOR_RESET_ALL = "إعادة تعيين الكل"
SETTINGS_CONTRAST_WARNING = (
    "تباين النص/الخلفية ضعيف: قد يصبح النص غير مقروء. "
    "اختر ألوانًا أكثر تباينًا أو أعد التعيين."
)
SETTINGS_SAVED_TOAST = "تم حفظ الإعدادات."

# --- منطقة الخطر
SETTINGS_DANGER_SECTION = "منطقة الخطر"
SETTINGS_RESET_BUTTON = "حذف الكل"
SETTINGS_RESET_EXPLAIN = (
    "حذف جميع البيانات نهائيًا: المنتجات، المبيعات، العملاء، "
    "المدفوعات، الصور، والإعدادات. إجراء غير قابل للرجوع."
)
RESET_DIALOG_TITLE = "حذف الكل"
RESET_DIALOG_WARNING = (
    "تحذير: هذا الإجراء يحذف نهائيًا جميع بيانات المتجر — "
    "المنتجات، المخزون، المبيعات، العملاء، المدفوعات، الصور "
    "والإعدادات. لا يمكن التراجع عنه."
)
RESET_DIALOG_PIN_PROMPT = "أدخل رمز PIN الخاص بالمالك للتأكيد:"
RESET_DIALOG_CONFIRM = "حذف الكل"
RESET_DONE = "تم حذف جميع البيانات. سيتم إغلاق التطبيق؛ " "أعد تشغيله للبدء من الصفر."

# --- إدارة المستخدمين
USER_NEW = "مستخدم جديد"
USER_EDIT = "تعديل"
USER_DEACTIVATE = "تعطيل"
USER_DIALOG_NEW = "مستخدم جديد"
USER_DIALOG_EDIT = "تعديل المستخدم"
USER_NAME = "الاسم"
USER_ROLE = "الدور"
USER_PIN = "الرمز السري"
USER_PIN_EDIT_HINT = "الرمز السري (اتركه فارغًا لعدم التغيير)"
USER_PIN_PLACEHOLDER = "••••"
USER_PIN_TOO_SHORT = "يجب أن يتكوّن الرمز السري من 4 أرقام على الأقل."
USER_ACTIVE = "نشط"
USER_COL_NAME = "الاسم"
USER_COL_ROLE = "الدور"
USER_COL_STATUS = "الحالة"
USER_STATUS_ACTIVE = "نشط"
USER_STATUS_INACTIVE = "غير نشط"
USER_EMPTY = "لا يوجد مستخدمون"
USER_SAVED_TOAST = "تم حفظ المستخدم."
USER_DEACTIVATED_TOAST = "تم تعطيل المستخدم."
USER_DEACTIVATE_CONFIRM = "تعطيل المستخدم « {name} »؟"

# --- العروض
PROMO_TYPE_LABELS = {
    "percent": "نسبة مئوية",
    "fixed": "مبلغ ثابت",
}
PROMO_NEW = "عرض جديد"
PROMO_DEACTIVATE = "تعطيل"
PROMO_DIALOG_NEW = "عرض جديد"
PROMO_CODE = "الرمز"
PROMO_CODE_PLACEHOLDER = "PROMO10"
PROMO_TYPE = "النوع"
PROMO_VALUE = "القيمة"
PROMO_VALUE_REQUIRED = "يجب أن تكون القيمة أكبر من الصفر."
PROMO_VALID_FROM = "صالح من"
PROMO_VALID_TO = "إلى"
PROMO_MAX_USES = "أقصى عدد استخدامات (0 = غير محدود)"
PROMO_UNLIMITED = "غير محدود"
PROMO_DATE_ORDER = "يجب أن يسبق تاريخ البداية تاريخ النهاية."
PROMO_COL_CODE = "الرمز"
PROMO_COL_TYPE = "النوع"
PROMO_COL_VALUE = "القيمة"
PROMO_COL_VALIDITY = "الصلاحية"
PROMO_COL_USES = "الاستخدامات"
PROMO_COL_STATUS = "الحالة"
PROMO_VALIDITY_RANGE = "من {start} إلى {end}"
PROMO_ACTIVE = "نشط"
PROMO_INACTIVE = "غير نشط"
PROMO_EMPTY = "لا توجد عروض"
PROMO_SAVED_TOAST = "تم إنشاء العرض."
PROMO_DEACTIVATED_TOAST = "تم تعطيل العرض."
PROMO_DEACTIVATE_CONFIRM = "تعطيل العرض « {code} »؟"

# ======================================================================
# 22. النسخ الاحتياطي، الملصقات، الاستيراد، التصدير والترقيم
# ======================================================================

# --- النسخ الاحتياطي والاستعادة
BACKUP_SECTION = "النسخ الاحتياطي والاستعادة"
BACKUP_HINT = (
    "أنشئ نسخة احتياطية من جميع بياناتك (المنتجات، المبيعات، "
    "العملاء، الصور). في حالة حدوث مشكلة، يمكنك استعادتها من ملف."
)
BACKUP_CREATE = "إنشاء نسخة احتياطية"
BACKUP_RESTORE = "استعادة نسخة احتياطية"
BACKUP_CREATING = "جاري إنشاء النسخة الاحتياطية…"
BACKUP_CREATED = "تم إنشاء النسخة الاحتياطية بنجاح."
BACKUP_RESTORE_CONFIRM = (
    "تحذير: الاستعادة تستبدل جميع البيانات الحالية "
    "ببيانات النسخة الاحتياطية. سيتم إنشاء نسخة أمان "
    "تلقائيًا قبل الاستبدال.\n\n"
    "أدخل رمز PIN لتأكيد ذلك:"
)
BACKUP_RESTORE_TITLE = "استعادة نسخة احتياطية"
BACKUP_RESTORE_SUCCESS = (
    "تمت الاستعادة بنجاح. سيتم إغلاق التطبيق؛ "
    "أعد تشغيله لاستخدام البيانات المستعادة."
)
BACKUP_RESTORE_FAILED = "فشل الاستعادة: {error}"
BACKUP_FILE_FILTER = "نسخ احتياطية (*.zip)"

# --- استيراد CSV
IMPORT_BUTTON = "استيراد (CSV)"
IMPORT_DIALOG_TITLE = "نتائج الاستيراد"
IMPORT_CREATED = "تم الإنشاء: {count}"
IMPORT_UPDATED = "تم التحديث: {count}"
IMPORT_ERRORS = "الأخطاء: {count}"
IMPORT_COL_ROW = "السطر"
IMPORT_COL_ERROR = "الخطأ"
IMPORT_FILE_FILTER = "ملفات CSV (*.csv)"
IMPORT_DONE_TOAST = "اكتمل الاستيراد: تم إنشاء {created}، وتم تحديث {updated}."

# --- ملصقات الباركود
LABELS_TITLE = "طباعة الملصقات"
LABELS_SELECT_PRODUCTS = "المنتجات"
LABELS_SELECT_ALL = "تحديد الكل"
LABELS_SELECT_NONE = "إلغاء تحديد الكل"
LABELS_SELECTED_COUNT = "{n} محدد"
LABELS_PRODUCT_ROW = "{name}  ·  المخزون: {stock}"
LABELS_CONFIG = "الإعدادات"
LABELS_SIZE = "حجم الملصق"
LABELS_COPIES = "نسخ لكل منتج"
LABELS_SHOW_NAME = "إظهار الاسم"
LABELS_SHOW_PRICE = "إظهار السعر"
LABELS_SHOW_BARCODE = "إظهار الباركود"
LABELS_SHOW_STORE = "إظهار اسم المتجر"
LABELS_PRICE_LEVEL = "مستوى السعر"
LABELS_BARCODE_TYPE = "نوع الباركود"
LABELS_PREVIEW = "معاينة"
LABELS_PRINT = "طباعة"
LABELS_EXPORT = "تصدير PDF"
LABELS_NONE_SELECTED = "اختر منتجًا واحدًا على الأقل."
LABELS_GENERATING = "جارٍ إنشاء الملصقات…"
LABELS_SENT_TO_PRINTER = "تم إرسال الملصقات إلى الطابعة."

# --- تصدير عام
EXPORT_SAVED_TOAST = "تم حفظ الملف: {path}"
OPEN_PDF_FAILED = "تعذّر فتح ملف PDF: {path}"

# --- ترقيم الصفحات
PAGINATION_PREV = "السابق"
PAGINATION_NEXT = "التالي"
PAGINATION_PAGE = "صفحة {current} / {total}"
