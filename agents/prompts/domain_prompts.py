"""Marketing context cannot override statistical evidence."""
MARKETING_CONCEPT_DEFINITIONS = """
CONSUMER JOURNEY: Consideration değerlendirme, Purchase satın alma,
Recommendation tavsiye ve Complaint şikayet davranışlarını temsil edebilir.
Yalnızca şemada ve veride mevcut etiketleri kullan. Tweet hacmi gerçek satış,
pazar büyüklüğü, yeni tüketici sayısı veya nedensellik için doğrudan ölçüm değildir.
"""
BUSINESS_HEURISTIC_RULES = """
STRATEJİK ÇIKARIM: Hacim değişimini oran değişiminden ayır; payda, tarih aralığı,
veri kapsamı ve eksik gözlemleri açıkla. Şikayet artışı ürün arızası nedeniyle olabilir,
ancak tek başına böyle bir nedenselliği kanıtlamaz. Sıfır sonuç verinin bulunmaması
anlamına gelebilir. Hipotez kararı yalnızca hesaplanmış test sonucundan alınır;
p-değeri hipotezin doğru olma olasılığı değildir. Destek yüzdesi uydurma.
Doğrudan ölçümü [Ölçüldü], yorumu [Makul], kanıtsız iddiayı [Desteklenmeyen] etiketle.
"""


def get_domain_context_prompt():
    return MARKETING_CONCEPT_DEFINITIONS + "\n" + BUSINESS_HEURISTIC_RULES


def build_hypothesis_synthesis_prompt(hypothesis, sql_evidence):
    return (f"Hipotez: {hypothesis}\nKanıt: {sql_evidence}\n" + get_domain_context_prompt()
            + "\nHesaplanmış istatistiksel test yoksa kabul/red kararı verme.")
