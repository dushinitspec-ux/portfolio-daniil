"""Fixed bot phrases in the four supported languages."""

from app.language import Language

WELCOME = {
    Language.EN: (
        "Hello! I'm the virtual concierge of {hotel}. Ask me anything about the hotel: "
        "breakfast hours, Wi-Fi, the pool, transfers. If I don't know the answer, "
        "I'll pass your question to the reception team."
    ),
    Language.RU: (
        "Здравствуйте! Я виртуальный консьерж {hotel}. Спросите меня об отеле: время "
        "завтрака, Wi-Fi, бассейн, трансфер. Если я не знаю ответа, я передам вопрос "
        "сотрудникам ресепшена."
    ),
    Language.TR: (
        "Merhaba! Ben {hotel} sanal konsiyerjiyim. Otel hakkında her şeyi sorabilirsiniz: "
        "kahvaltı saatleri, Wi-Fi, havuz, transfer. Cevabı bilmiyorsam sorunuzu resepsiyon "
        "ekibine iletirim."
    ),
    Language.DE: (
        "Hallo! Ich bin der virtuelle Concierge des {hotel}. Fragen Sie mich alles über das "
        "Hotel: Frühstückszeiten, WLAN, Pool, Transfer. Wenn ich die Antwort nicht kenne, "
        "leite ich Ihre Frage an die Rezeption weiter."
    ),
}

ESCALATED = {
    Language.EN: (
        "I don't have this information, so I've passed your question to our reception "
        "team. They will reply here shortly."
    ),
    Language.RU: (
        "У меня нет этой информации, поэтому я передал ваш вопрос на ресепшен. "
        "Сотрудники скоро ответят вам здесь."
    ),
    Language.TR: (
        "Bu bilgiye sahip değilim, bu yüzden sorunuzu resepsiyon ekibimize ilettim. "
        "Kısa süre içinde buradan yanıt verecekler."
    ),
    Language.DE: (
        "Diese Information habe ich leider nicht, daher habe ich Ihre Frage an unsere "
        "Rezeption weitergeleitet. Sie erhalten hier in Kürze eine Antwort."
    ),
}

# Used when the question cannot be delivered to staff (no staff chat, Telegram error):
# better to send the guest to the desk than to promise a reply that will never come.
ESCALATION_UNAVAILABLE = {
    Language.EN: "I don't have this information. Please ask at the reception desk.",
    Language.RU: "У меня нет этой информации. Пожалуйста, обратитесь на ресепшен.",
    Language.TR: "Bu bilgiye sahip değilim. Lütfen resepsiyona danışın.",
    Language.DE: "Diese Information habe ich leider nicht. Bitte wenden Sie sich an die Rezeption.",
}

STAFF_REPLY_HEADER = {
    Language.EN: "💬 Reply from reception:",
    Language.RU: "💬 Ответ ресепшена:",
    Language.TR: "💬 Resepsiyonun yanıtı:",
    Language.DE: "💬 Antwort der Rezeption:",
}

TRANSLATED_NOTE = {
    Language.EN: "Translated automatically. Original:",
    Language.RU: "Переведено автоматически. Оригинал:",
    Language.TR: "Otomatik olarak çevrildi. Orijinal:",
    Language.DE: "Automatisch übersetzt. Original:",
}

TEXT_ONLY = {
    Language.EN: "Please write your question as a text message.",
    Language.RU: "Пожалуйста, напишите вопрос текстом.",
    Language.TR: "Lütfen sorunuzu yazılı mesaj olarak gönderin.",
    Language.DE: "Bitte schreiben Sie Ihre Frage als Textnachricht.",
}

RATE_LIMITED = {
    Language.EN: "You're sending messages very quickly. Please wait a minute.",
    Language.RU: "Вы отправляете сообщения слишком часто. Подождите, пожалуйста, минуту.",
    Language.TR: "Çok hızlı mesaj gönderiyorsunuz. Lütfen bir dakika bekleyin.",
    Language.DE: "Sie senden sehr schnell Nachrichten. Bitte warten Sie eine Minute.",
}
