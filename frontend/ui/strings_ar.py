"""Centralized user-facing strings — Arabic.

Every user-visible string in the application lives here; widgets never
hardcode text. When Arabic (RTL) ships, this module is swapped for a
QTranslator-based mechanism without touching screen code.
"""

APP_TITLE = "إدارة المخزون ونقاط البيع"

# --- Générique
OK = "تأكيد"
CANCEL = "إلغاء"
CLOSE = "إغلاق"
SAVE = "حفظ"
DELETE = "أرشفة"
EDIT = "تعديل"
SEARCH = "بحث…"
REFRESH = "تحديث"
CONFIRM_TITLE = "تأكيد"
ERROR_TITLE = "خطأ"
INFO_TITLE = "معلومات"
REQUIRED_FIELD = "هذا الحقل إلزامي."
LOADING = "جاري التحميل"
PIN_REQUIRED_ACTION = (
    "يتطلب هذا الإجراء رمز PIN الخاص بالمالك. "
    "أعد تشغيل التطبيق وأدخل رمز PIN."
)

# --- Erreurs techniques (non bloquantes, langage non technique)
API_STARTUP_ERROR_TITLE = "خطأ في بدء التشغيل"
API_STARTUP_ERROR_TEXT = (
    "تعذر بدء تشغيل الخدمة المحلية. "
    "يرجى إغلاق التطبيق ثم إعادة تشغيله."
)
NETWORK_ERROR = (
    "الخدمة المحلية لا تستجيب. "
    "يرجى الانتظار بضع ثوانٍ ثم المحاولة مرة أخرى."
)
UNEXPECTED_ERROR = "حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى."

# --- Licence et Mise à jour
LICENSE_ERROR_TITLE = "خطأ في الترخيص"
LICENSE_MISSING = "ملف الترخيص غير موجود. يرجى وضع ملف license.lic في مجلد التطبيق."
UPDATE_AVAILABLE = "يتوفر إصدار جديد ({version})!"
UPDATE_AVAILABLE_HINT = "قم بتنزيله من: {url}"

# --- Connexion / PIN
ONBOARDING_TITLE = "مرحبًا بك في إدارة المخزون ونقاط البيع"
ONBOARDING_WELCOME = "الإعداد الأول"
ONBOARDING_DESC = "يرجى تعيين رمز PIN (كلمة مرور) لحماية الوصول إلى نقطة البيع الخاصة بك. سيُطلب هذا الرمز عند كل تشغيل."
ONBOARDING_PIN_PROMPT = "تعيين رمز PIN:"
ONBOARDING_PIN_CONFIRM = "تأكيد رمز PIN"
ONBOARDING_SUBMIT = "البدء"
ONBOARDING_ERR_EMPTY = "لا يمكن أن يكون رمز PIN فارغًا."
ONBOARDING_ERR_MISMATCH = "رمزا PIN غير متطابقين."

# --- Visite Guidée (Feature Tour)
FEATURE_TOUR_TITLE = "استكشاف التطبيق"
FEATURE_TOUR_WELCOME = "مرحبًا بك في إدارة المخزون ونقاط البيع!"
FEATURE_TOUR_CHECKOUT_TITLE = "نقطة البيع (الكاشير)"
FEATURE_TOUR_CHECKOUT_DESC = "أنجز مبيعاتك بسرعة. ابحث باستخدام الباركود أو الاسم، وطبق الخصومات، وقم بالتحصيل نقدًا أو بالبطاقة."
FEATURE_TOUR_INVENTORY_TITLE = "المخزون"
FEATURE_TOUR_INVENTORY_DESC = "أدر منتجاتك، وأسعار الجملة والتجزئة، وراقب مستويات المخزون."
FEATURE_TOUR_STATS_TITLE = "الإحصائيات والتقارير"
FEATURE_TOUR_STATS_DESC = "تتبع إيراداتك، وأفضل المبيعات، وصدر التقارير (PDF، Excel) لمحاسبتك."
FEATURE_TOUR_ALERTS_TITLE = "التنبيهات والديون"
FEATURE_TOUR_ALERTS_DESC = "احصل على إشعارات بانخفاض المخزون وتتبع ديون العملاء قيد الانتظار."
FEATURE_TOUR_PRINT_TITLE = "الطباعة والملصقات"
FEATURE_TOUR_PRINT_DESC = "اطبع إيصالات الدفع على طابعتك الحرارية (ESC/POS) وأنشئ ملصقات الباركود لأصنافك."

LOGIN_TITLE = "رمز PIN"
LOGIN_PROMPT = "أدخل رمز PIN لفتح التطبيق:"
LOGIN_PLACEHOLDER = "رمز PIN"
LOGIN_BUTTON = "فتح"
PIN_NOT_CONFIGURED = (
    "لم يتم تكوين رمز PIN. يفتح التطبيق بدون حماية.\n"
    "لتعيين واحد: python scripts/set_pin.py <PIN>"
)

# --- Barre de titre
TITLEBAR_MINIMIZE = "تصغير"
TITLEBAR_MAXIMIZE = "تكبير"
TITLEBAR_RESTORE = "استعادة"
TITLEBAR_FULLSCREEN = "ملء الشاشة (F11)"
TITLEBAR_EXIT_FULLSCREEN = "الخروج من ملء الشاشة (F11)"
TITLEBAR_CLOSE = "إغلاق"

# --- Navigation
NAV_CHECKOUT = "نقطة البيع"
NAV_INVENTORY = "المخزون"
NAV_CUSTOMERS = "العملاء"
NAV_STATISTICS = "الإحصائيات"
NAV_ALERTS = "التنبيهات"
NAV_SETTINGS = "الإعدادات"
NAV_SECTION = "القائمة"

# --- Niveaux de prix (partout : caisse, stock, fiches)
PRICE_DETAIL = "تجزئة"
PRICE_GROS = "جملة"
PRICE_SUPER_GROS = "جملة الجملة"
PRICE_LEVEL_LABELS = {
    "detail": PRICE_DETAIL,
    "gros": PRICE_GROS,
    "super_gros": PRICE_SUPER_GROS,
}

# --- Prix manuel (sélecteur de niveau de prix, caisse)
PRICE_LEVEL_MANUAL = "يدوي"
CHECKOUT_MANUAL_PRICE_TIP = "تم إدخال السعر يدويًا (أعلى من الحد الأدنى)."

# --- Conditionnements (colisage) : caisse + fiche produit
PACKAGING_UNIT = "وحدة"
CHECKOUT_COL_PACKAGING = "التعبئة"
PRODUCT_PACKAGINGS = "التعبئة (اختياري)"
PACKAGING_ADD = "إضافة تعبئة"
PACKAGING_LABEL = "الاسم (مثل كرتونة)"
PACKAGING_LABEL_COL = "الاسم"
PACKAGING_UNITS_COL = "الوحدات/العبوة"
PACKAGING_UNIT_COUNT = "الوحدات في العبوة"
PACKAGING_REMOVE = "إزالة"
PACKAGING_HINT = (
    "لكل تعبئة سعرها الخاص وتستهلك عدد معين من وحدات المخزون."
)
CHECKOUT_BASE_UNITS = "{n} وحدات"

# --- Caisse
CHECKOUT_TITLE = "نقطة البيع"
CHECKOUT_SEARCH_PLACEHOLDER = (
    "امسح الباركود أو اكتب اسمًا… (اضغط Enter للإضافة)"
)
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
CHECKOUT_REMOVE_LINE = "إزالة السطر"
CHECKOUT_DONE_TOAST = "تم تسجيل البيع — جاري طباعة الإيصال…"
CHECKOUT_NO_RESULT = "لم يتم العثور على منتج لـ «{query}»."
CHECKOUT_STOCK_BADGE = "المخزون {count}"
CHECKOUT_OUT_OF_STOCK = "نفد من المخزون"
CHECKOUT_CUSTOMER_LABEL = "العميل:"
CHECKOUT_CUSTOMER_ANONYMOUS = "مجهول"
CHECKOUT_CUSTOMER_CLEAR = "إزالة العميل"
RECEIPT_PRINT_FAILED = (
    "تم حفظ الإيصال ولكن تعذر إرساله إلى الطابعة.\n"
    "الملف: {path}"
)

# --- Paiement (dialogue d'encaissement)
PAYMENT_TITLE = "التحصيل"
PAYMENT_TOTAL_LABEL = "إجمالي الدفع"
PAYMENT_FULL = "دفع كامل"
PAYMENT_PARTIAL = "دفع جزئي (دين/ائتمان)"
PAYMENT_AMOUNT_LABEL = "المبلغ المدفوع الآن"
PAYMENT_REMAINING_LABEL = "المبلغ المتبقي"
PAYMENT_CUSTOMER_REQUIRED = (
    "يجب ربط الدفع الجزئي بعميل (الاسم ورقم الهاتف)."
)
PAYMENT_CONFIRM = "دفع"
PAYMENT_RECORD_TITLE = "تسجيل دفعة"
PAYMENT_RECORD_BALANCE = "الرصيد المتبقي: {balance}"
PAYMENT_RECORD_DONE = "تم تسجيل دفعة بقيمة {amount}."
PAYMENT_AMOUNT_TOO_HIGH = "المبلغ يتجاوز الرصيد المتبقي."
PAYMENT_AMOUNT_REQUIRED = "أدخل مبلغًا أكبر من الصفر."

# --- Clients
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
CUSTOMER_TOP_HINT = (
    "الترتيب حسب الإيرادات — حدد عميلاً للتفاصيل."
)
CUSTOMER_COL_DATE = "التاريخ"
CUSTOMER_COL_TOTAL = "الإجمالي"
CUSTOMER_COL_PAID = "المدفوع"
CUSTOMER_COL_BALANCE = "المتبقي"
CUSTOMER_COL_STATUS = "الحالة"

# --- Stock / Inventaire
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
    "هل تريد أرشفة المنتج «{name}»؟\n"
    "لن يكون قابلاً للبيع ولكنه سيبقى في السجل."
)
INVENTORY_SELECT_ROW_FIRST = "يرجى تحديد منتج من القائمة أولاً."
INVENTORY_LOW_STOCK_BADGE = "مخزون منخفض"
INVENTORY_EMPTY = "لا يوجد منتجات في المخزون"
INVENTORY_EMPTY_HINT = "أنشئ منتجك الأول للبدء في البيع."
INVENTORY_DETAIL_HINT = "نقر مزدوج على المنتج: عرض التفاصيل والإحصائيات."
YES = "نعم"
NO = "لا"

# --- Fiche produit (formulaire)
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
PRODUCT_IMAGE_UPLOAD_FAILED = (
    "تم حفظ المنتج ولكن تعذر إرسال الصورة: {reason}"
)
PRODUCT_SAVED_TOAST = "تم حفظ المنتج «{name}»."

# --- Fiche produit (détail + statistiques)
PRODUCT_DETAIL_TITLE = "تفاصيل المنتج"
PRODUCT_DETAIL_STATS = "مبيعات المنتج"
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

# --- Statistiques
STATISTICS_TITLE = "الإحصائيات"
STATS_EXPORT_PDF = "تصدير PDF"
STATS_EXPORT_XLSX = "تصدير Excel"
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
STATS_VS_PREVIOUS = "مقارنة بالفترة السابقة"
STATS_FROM = "من"
STATS_TO = "إلى"
STATS_TOP_PRODUCTS = "أفضل المبيعات"
STATS_COL_PRODUCT = "المنتج"
STATS_COL_QTY = "الكمية المباعة"
STATS_COL_REVENUE = "الإيرادات"
STATS_ASSOCIATIONS = "منتجات تُشترى معًا غالبًا"
STATS_ASSOCIATION_RULE = (
    "العملاء الذين يشترون {antecedent} يأخذون أيضًا {consequent}"
)
STATS_ASSOCIATION_DETAIL = (
    "الثقة {confidence} % · الدعم {support} % · الرفع {lift}"
)
STATS_ASSOCIATIONS_EMPTY = "لا يوجد مبيعات كافية لاكتشاف الارتباطات بعد"
STATS_ASSOCIATIONS_EMPTY_HINT = (
    "تظهر الارتباطات عندما يتم شراء المنتجات معًا "
    "في العديد من المبيعات خلال الفترة."
)
STATS_PIN_REQUIRED = "الإحصائيات تتطلب رمز PIN الخاص بالمالك."

# --- Alertes
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

# --- Réglages
SETTINGS_TITLE = "الإعدادات"
SETTINGS_RECEIPT_SECTION = "تخصيص الإيصال"
SETTINGS_SHOP_NAME = "اسم المتجر"
SETTINGS_PHONE = "الهاتف"
SETTINGS_ADDRESS = "العنوان"
SETTINGS_FOOTER = "رسالة التذييل"
SETTINGS_SHOW_CREDIT = "طباعة المدفوع / المتبقي في مبيعات الديون"
SETTINGS_PREVIEW_TITLE = "معاينة الإيصال"
SETTINGS_LANGUAGE_SECTION = "اللغة"
SETTINGS_LANGUAGE_FR = "الفرنسية (Français)"
SETTINGS_LANGUAGE_AR = "العربية"
SETTINGS_PRINTER_SECTION = "الطباعة"
SETTINGS_PRINTER_HINT = "اختيار الطابعة خاص بهذا الحاسوب."
SETTINGS_PRINTER_DEFAULT = "طابعة النظام الافتراضية"
SETTINGS_PRINTER_TEST = "صفحة اختبار"
SETTINGS_PRINTER_ESCPOS = "وضع حراري ESC/POS (درج النقود)"
SETTINGS_PRINTER_DRAWER = "فتح درج النقود"
SETTINGS_PRINTER_TEST_SENT = "تم إرسال صفحة الاختبار إلى الطابعة."
SETTINGS_ACCENT_SECTION = "لون التمييز"
SETTINGS_ACCENT_CUSTOM = "مخصص…"
SETTINGS_SAVED_TOAST = "تم حفظ الإعدادات."
SETTINGS_RESTART_REQUIRED = "تم تغيير لغة الواجهة. يرجى إعادة تشغيل التطبيق لتطبيق التغيير."
SETTINGS_PREVIEW_SAMPLE_PRODUCT = "مثال لمنتج"
SETTINGS_PREVIEW_TOTAL = "الإجمالي"
SETTINGS_PREVIEW_PAID = "المدفوع"
SETTINGS_PREVIEW_REMAINING = "المبلغ المتبقي"
SETTINGS_PREVIEW_CUSTOMER = "العميل: علي بن علي"
SETTINGS_PREVIEW_DEFAULT_FOOTER = "شكرًا لزيارتكم!"
SETTINGS_PREVIEW_TICKET = "تذكرة رقم A1B2C3D4"

# --- Zone dangereuse (réinitialisation totale)
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
RESET_DONE = (
    "تم حذف جميع البيانات. سيتم إغلاق التطبيق؛ "
    "أعد تشغيله للبدء من الصفر."
)

# ============================================================================
# Client attaché + vente anonyme + recherche intelligente
# (Customer Attach + Guest Sale + Smart Search)
# ----------------------------------------------------------------------------

# --- Widget de recherche client (CustomerSearchBox, partagé)
CUSTOMER_SEARCH_PLACEHOLDER = "البحث عن عميل (الاسم أو الهاتف)…"
CUSTOMER_SEARCH_NO_RESULT = "لم يتم العثور على عملاء."
CUSTOMER_SEARCH_CREATE = "إنشاء «{query}»…"
CUSTOMER_ATTACH = "إرفاق"
CUSTOMER_DETACH = "إزالة العميل"
CUSTOMER_ANONYMOUS = "مجهول"

# --- Paiement partiel : attacher ou créer un client (nom + téléphone requis)
# NB : le message d'exigence réutilise PAYMENT_CUSTOMER_REQUIRED (déjà défini).
PAYMENT_PARTIAL_NEED_CUSTOMER = PAYMENT_CUSTOMER_REQUIRED
PAYMENT_NEW_CUSTOMER_NAME = "اسم العميل"
PAYMENT_NEW_CUSTOMER_PHONE = "الهاتف"
PAYMENT_ATTACH_EXISTING = "عميل حالي"
PAYMENT_CREATE_NEW = "عميل جديد"

# --- Écran Ventes (journal des ventes)
NAV_SALES = "المبيعات"
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

# --- Dialogue Détail de la vente (résolution du client)
SALE_DETAIL_TITLE = "تفاصيل البيع"
SALE_RESOLVE_SECTION = "عميل هذه العملية"
SALE_LEAVE_ANONYMOUS = "ترك كمجهول"
SALE_CREATE_CUSTOMER = "إنشاء عميل"
SALE_ATTACH_CUSTOMER = "إرفاق عميل حالي"
SALE_ASSIGNED_DONE = "تم إرفاق العميل بعملية البيع."
SALE_LEFT_ANONYMOUS_DONE = "تم تمييز البيع كمجهول."
SALE_ALREADY_HAS_CUSTOMER = "هذه العملية مرتبطة بعميل بالفعل."
SALE_REPRINT_RECEIPT = "إعادة طباعة الإيصال"

# --- Sauvegarde et restauration
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

# --- Avoirs (remboursements)
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
RECEIPT_PRINT_FAILED = "فشل الطباعة: {path}"

# --- Remise (discount per cart line)
CHECKOUT_COL_DISCOUNT = "الخصم"
CHECKOUT_DISCOUNT_TIP = "تم تطبيق الخصم على السطر (تم اعتماده بواسطة الخادم)."

# --- Mode de paiement
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

# --- Statistiques : remises et modes de paiement
STATS_DISCOUNTS = "الخصومات الممنوحة"
STATS_PAYMENT_METHODS = "التوزيع حسب طريقة الدفع"
STATS_PM_COL_METHOD = "الطريقة"
STATS_PM_COL_TOTAL = "المبلغ"
STATS_PM_COL_COUNT = "المعاملات"

# --- Fournisseurs
NAV_SUPPLIERS = "الموردون"
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
SUPPLIER_STAT_ORDERS = "الطلبات"
SUPPLIER_STAT_TOTAL = "إجمالي المشتريات"
SUPPLIER_STAT_BALANCE = "الديون الحالية"
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

# --- Réception de stock (purchase order)
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

# --- Import CSV
IMPORT_BUTTON = "استيراد (CSV)"
IMPORT_DIALOG_TITLE = "نتائج الاستيراد"
IMPORT_CREATED = "تم الإنشاء: {count}"
IMPORT_UPDATED = "تم التحديث: {count}"
IMPORT_ERRORS = "الأخطاء: {count}"
IMPORT_COL_ROW = "السطر"
IMPORT_COL_ERROR = "الخطأ"
IMPORT_FILE_FILTER = "ملفات CSV (*.csv)"
IMPORT_DONE_TOAST = "اكتمل الاستيراد: تم إنشاء {created}، وتم تحديث {updated}."
