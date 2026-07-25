import { ACCOUNT_DELETION_GRACE_DAYS } from '@/lib/constants';
import { LEGAL_ENTITY } from './config';

const { brand, operatorName, country, privacyEmail, contactEmail } = LEGAL_ENTITY;

/**
 * Turkish-language KVKK aydınlatma metni (privacy notice). Mirrors the section
 * structure of the English {@link PRIVACY} so the two can be maintained in
 * lockstep, but is written natively in Turkish legal terminology rather than
 * machine-translated. The English text remains the governing version; this
 * satisfies KVKK's expectation that the notice be available in a language the
 * data subject understands.
 */
export const PRIVACY_TR = `
## 1. Kapsam

Bu metin, ${brand} olarak hangi kişisel verilerinizi hangi amaçla işlediğimizi,
bu verileri ne kadar süreyle sakladığımızı ve bu konuda sahip olduğunuz hakları
açıklar. Metin, hem 6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK) hem de
Avrupa Birliği/Birleşik Krallık Genel Veri Koruma Tüzüğü (GDPR) kapsamındaki
yükümlülüklerimizi karşılamak üzere hazırlanmıştır.

## 2. Veri Sorumlusu

${country}'de mukim gerçek kişi ${operatorName}, bu metinde açıklanan kişisel verilerin
**veri sorumlusudur** (GDPR: *data controller*). Bu metinle ilgili her konuda
${privacyEmail} adresinden bize ulaşabilirsiniz.

### 2.1 Veri sorumlusu ve veri işleyen ayrımı

Hesabınıza, faturalandırmanıza ve platform kullanımınıza ilişkin veriler
bakımından **veri sorumlusuyuz**: bu verilerin neden ve nasıl işleneceğine biz
karar veririz.

Bir modele ilettiğiniz içerik — istemleriniz (prompt), yüklediğiniz dokümanlar ve
ajanların ürettiği çıktılar — bakımından ise **talimatınız üzerine hareket eden
veri işleyen** konumundayız. Hangi model sağlayıcının çağrılacağını, kendi API
anahtarınızı bağlayarak siz seçersiniz. Bir ajan istemininizi OpenAI, Anthropic
veya Google'a gönderdiğinde, bunu sizin yapılandırmanız nedeniyle yapar. Bu
sağlayıcılar, anahtarınızı edinirken kabul ettiğiniz kendi koşulları uyarınca
bağımsız veri sorumlusu veya veri işleyen konumundadır.

## 3. İşlediğimiz Kişisel Veriler

### 3.1 Sizin bize verdiğiniz veriler

| Veri | Neden işliyoruz |
| --- | --- |
| E-posta adresi | Hesabınızı tanımlamak, oturum açmanızı sağlamak ve Hizmet hakkında sizinle iletişim kurmak için |
| Parola | Yalnızca Argon2 özeti (hash) olarak saklanır. Parolanızı hiçbir zaman göremeyiz |
| Görünen ad (isteğe bağlı) | Arayüzü kişiselleştirmek için |
| Model sağlayıcı API anahtarları | Seçtiğiniz sağlayıcıları sizin adınıza çağırmak için. AES-256-GCM ile şifrelenir; tarayıcıya asla geri döndürülmez |
| İstemler, görev geçmişi, ajan çıktıları | Görevlerinizi yürütmek ve sonuçlarını size göstermek için |
| Yüklenen dokümanlar | Ajan yanıtlarını kendi materyalinize dayandırmak (retrieval) için |
| Özel ajan yapılandırmaları | Ajan ekipleri oluşturup yeniden kullanabilmeniz için |
| Kart markası, son dört hane, son kullanma tarihi | Kayıtlı kartınızı size gösterebilmek için |

**Kart numaranızın tamamını asla saklamayız.** Bu bilgi, yalnızca ödeme
kuruluşuna yapılan tek bir çağrı süresince bellekte bulunur; hiçbir veritabanına,
kayda (log) veya API yanıtına yazılmaz.

### 3.2 Hizmeti kullanırken oluşan veriler

- **Kullanım kayıtları** — görev başına tüketilen token miktarı, kullanılan
  sağlayıcı ve görevin başarılı olup olmadığı. Kotanız bu kayıtlar üzerinden
  uygulanır ve panonuz bu kayıtlardan oluşturulur.
- **Ajan kayıtları (log)** — bir görevin adım adım izi; ajanlarınızın ne yaptığını
  Architect görünümünde inceleyebilmeniz için tutulur.
- **Konuşma hafızası ve doküman gömmeleri (embedding)** — ajanların ilgili bağlamı
  hatırlayabilmesi için geçmiş konuşmalarınızın ve dokümanlarınızın vektör
  temsilleri. Bunlar kullanıcı kimliğinize (user id) bağlıdır ve başka bir
  kullanıcı tarafından hiçbir şekilde aranamaz.

### 3.3 İşlemediğimiz veriler

Hiçbir üçüncü taraf analitik, reklam veya siteler arası takip aracı
çalıştırmıyoruz. Sizin hakkınızda profil oluşturmuyoruz. Kişisel verilerinizi
satmıyoruz ve hiçbir zaman satmadık. İçeriğinizi model eğitmek için
kullanmıyoruz.

### 3.4 Anonim kullanım istatistikleri (isteğe bağlı)

Hizmet'in bazı kurulumları, yalnızca **herkese açık tanıtım sayfalarındaki**
ziyaretleri saymak için — oturum açılan ürünün içinde asla — kendi
altyapımızda barındırdığımız açık kaynaklı [Umami](https://umami.is) analitik
aracını çalıştırır.

Bu araç yalnızca **açık rızanızla** çalışır (KVKK Md. 5/1; GDPR Md. 6/1-a):
hiçbir şey yüklenmeden önce sorulur ve reddetmek, kabul etmek kadar kolaydır.
Çerezsizdir: tarayıcınıza hiçbir tanımlayıcı yazılmaz, ziyaretçiler düzenli
olarak yenilenen tuzlu bir özet (salted hash) ile ayırt edilir ve IP adresleri
saklanmaz. Kaydedilenler: görüntülenen sayfa, yönlendiren sayfa, tarayıcı,
işletim sistemi, cihaz türü, ülke ve ekran boyutu — sizi adlandıran hiçbir şey.

Kendi sunucumuzda barındırıldığı için bu veriler sunucumuzdan hiç çıkmaz ve ek
bir alt veri işleyen devreye girmez. Rızanızı istediğiniz an
[Çerez Politikası](/cookies) sayfasından geri çekebilirsiniz; geri çekme,
veri toplamayı derhâl durdurur.

## 4. İşleme Amaçları ve Hukuki Sebepler (KVKK Md. 5 / GDPR Md. 6)

| Amaç | KVKK hukuki sebebi | GDPR hukuki sebebi |
| --- | --- | --- |
| Talep ettiğiniz Hizmet'in sunulması | Bir sözleşmenin ifası için gereklilik | Sözleşmenin ifası |
| Ödemenin alınması, dolandırıcılığın önlenmesi | Sözleşmenin ifası için gereklilik; meşru menfaat | Sözleşmenin ifası; meşru menfaat |
| Platformun güvenliğinin sağlanması, kötüye kullanımın önlenmesi | Meşru menfaat | Meşru menfaat |
| Vergi, muhasebe ve hukuki yükümlülüklerin yerine getirilmesi | Kanunlarda açıkça öngörülmesi | Hukuki yükümlülük |
| Destek taleplerinizin yanıtlanması | Meşru menfaat | Meşru menfaat |
| Herkese açık sayfalarda anonim ziyaret istatistikleri (etkinse) | Açık rıza (Md. 5/1) | Rıza (Md. 6/1-a) |

Meşru menfaate dayandığımız hâllerde, bu menfaati haklarınız ve özgürlükleriniz
karşısında değerlendirdik ve söz konusu menfaatin bunları zedelemediği sonucuna
vardık. İşlemeye itiraz edebilirsiniz — bkz. 8. bölüm.

## 5. Kişisel Verilerin Kimlerle Paylaşıldığı

Kişisel verilerinizi yalnızca aşağıdaki veri işleyenlerle ve her birinin işini
yapması için gereken ölçüde paylaşırız. Verilerinizi satmayız ve reklam
verenlere açıklamayız.

### 5.1 Alt veri işleyenler

| Alt veri işleyen | Ne yapar | Eriştiği veri |
| --- | --- | --- |
| Bağladığınız model sağlayıcıları (OpenAI, Anthropic, Google veya diğerleri) | Ajanlarınızın talep ettiği çıkarımı (inference) yürütür | Ajanlarınızın gönderdiği istemler, bağlam ve dokümanlar |
| Barındırma ve veritabanı altyapımız | Uygulamayı çalıştırır ve verilerini saklar | Hizmet tarafından saklanan tüm veriler (durağan hâlde) |
| Ödeme kuruluşu | Abonelik ödemesini tahsil eder | Kart bilgileriniz ve faturalandırma tanımlayıcılarınız |

Model sağlayıcıları, bağladığınız anahtar aracılığıyla **sizin tarafınızdan**
devreye alınır. Yalnızca yerel modeli kullanırsanız, istemleriniz altyapımızdan
hiç çıkmaz.

Analitik (bölüm 3.4) bu listeye hiçbir şey eklemez: aynı altyapıda
barındırıldığı için bu veriyi hiçbir üçüncü taraf almaz.

Bu listedeki esaslı değişiklikleri, yürürlüğe girmeden önce yayımlarız.

### 5.2 Diğer aktarımlar

Kişisel verilerinizi, hukuken zorunlu olduğumuz hâllerde, bir hukuki talebin
tesisi veya savunması için gerekli olduğunda ya da bir kişinin güvenliğine
yönelik yakın bir tehlike bulunduğunda açıklayabiliriz. Verilerinizi açıklamaya
zorlanırsak, hukuken engellenmediğimiz sürece sizi bilgilendiririz.

### 5.3 Kurumsal müşteriler

Bir Veri İşleme Sözleşmesine (DPA) ihtiyaç duyarsanız, ${privacyEmail} adresine
yazın; size bir tane sağlayalım.

## 6. Yurt Dışına Aktarım (KVKK Md. 9)

${country}'de yerleşiğiz. Ajanlarınız başka bir ülkede bulunan bir model
sağlayıcısını çağırdığında — çoğu Amerika Birleşik Devletleri'ndedir —
isteminiz oraya aktarılır. Bu aktarım, o sağlayıcıyı yapılandırmanız nedeniyle
gerçekleşir.

Veri sorumlusu sıfatıyla kişisel verileri AEA, Birleşik Krallık veya ${country}
dışına aktardığımız hâllerde, yeterlilik kararı bulunuyorsa ona; bulunmuyorsa
Standart Sözleşme Hükümleri'ne veya KVKK kapsamındaki eşdeğer taahhütnameye
dayanırız.

## 7. Saklama Süreleri

| Veri | Saklama süresi |
| --- | --- |
| Hesap, abonelik, API anahtarı kayıtları | Hesabınızı silene kadar |
| Görev oturumları ve ajan kayıtları | Platformun saklama penceresi dolduğunda otomatik olarak; hesabınızı silerseniz daha erken sona erer |
| Konuşma hafızası, doküman parçaları | Dokümanı silene ya da hesabınızı silene kadar |
| Kullanım kayıtları | Hesabınızı silene kadar |
| Faturalandırma ve vergi kayıtları | Vergi ve muhasebe mevzuatının gerektirdiği süre boyunca, hesap silindikten sonra da |
| Anonim ziyaret istatistikleri (etkinse) | Toplu ve anonim sayımlardır; hesabınızla ilişkilendirilmez ve sizi tanımlayan hiçbir şey içermediği için hesap silme kapsamına girmez |

### 7.1 Hesabınızın silinmesi

Profil ayarlarınızdan istediğiniz zaman silme talep edebilirsiniz. Talep
ettiğinizde:

1. Hesabınız **derhâl kilitlenir**. Görev başlatamaz, kota harcayamaz veya ürünün
   hiçbir kısmını kullanamazsınız. Yeniden faturalandırılmamanız için ücretli
   aboneliğiniz iptal edilir.
2. **${ACCOUNT_DELETION_GRACE_DAYS} gün** boyunca oturum açıp hesabı geri
   yükleyebilirsiniz. Bu süre, kazara veya kötü niyetli bir silmenin geri
   alınabilmesi için tanınır. Geri yükleme, iptal edilen aboneliği yeniden
   başlatmaz.
3. ${ACCOUNT_DELETION_GRACE_DAYS} günün sonunda her şey **kalıcı ve geri
   dönülmez biçimde silinir**: hesap kaydınız ve ona bağlı her şey (API
   anahtarları, abonelik, ödeme yöntemi, kullanım kayıtları), görev
   oturumlarınız, ajan kayıtlarınız, dokümanlarınız ve özel ajanlarınız ile
   vektör deposundaki konuşma hafızalarınız ve doküman gömmeleriniz.

Pazar Yeri'nde (Marketplace) yayımladığınız ajan ekipleri bir istisnadır. Bunlar
**silinmez**, çünkü başka kullanıcılar bu ekipleri kurmuş olabilir. Bunun yerine,
öğe ile aranızdaki bağı koparırız: yazar tanımlayıcısı kaldırılır ve öğe yalnızca
"Topluluk"a atfedilebilir hâle gelir. İçeriğin kendisi artık sizinle ilgili bir
kişisel veri değildir. Yayımlanan bir öğe, içine yazdığınız kişisel bir veri
içeriyorsa ${privacyEmail} adresine bildirin; öğeyi kaldıralım.

Silme işleminden önce, hakkınızda tuttuğumuz her şeyi profil ayarlarınızdan bir
JSON dosyası olarak indirebilirsiniz.

## 8. İlgili Kişi Olarak Haklarınız

KVKK Md. 11 uyarınca; kişisel verinizin işlenip işlenmediğini öğrenme, işlenmişse
buna ilişkin bilgi talep etme, işlenme amacını ve bunların amacına uygun
kullanılıp kullanılmadığını öğrenme, yurt içinde veya yurt dışında verilerin
aktarıldığı üçüncü kişileri bilme, eksik veya yanlış işlenmiş verilerin
düzeltilmesini isteme, verilerin silinmesini veya yok edilmesini isteme, düzeltme
ve silme işlemlerinin verilerin aktarıldığı üçüncü kişilere bildirilmesini isteme,
münhasıran otomatik sistemlerle analiz edilmesi sonucu aleyhinize bir sonucun
ortaya çıkmasına itiraz etme ve verilerin hukuka aykırı işlenmesi nedeniyle
zarara uğramanız hâlinde zararın giderilmesini talep etme haklarına sahipsiniz.

GDPR uyarınca ise; verilerinize erişme (Md. 15), düzeltilmesini isteme (Md. 16),
silinmesini isteme (Md. 17), işlenmesinin kısıtlanmasını isteme (Md. 18),
verilerinizin taşınabilirliği (Md. 20) ve meşru menfaate dayalı işlemeye itiraz
etme (Md. 21) haklarına sahipsiniz.

Bu hakların çoğunu kendiniz kullanabilirsiniz: profil ayarları sayfası
verilerinizi düzenlemenize, tümünü dışa aktarmanıza ve hesabınızı silmenize olanak
tanır. Bunun dışındaki her konu için ${privacyEmail} adresine yazın. KVKK
kapsamındaki başvurularınızı en geç **otuz gün** içinde, GDPR kapsamındaki
taleplerinizi ise **bir ay** içinde yanıtlarız. Talebiniz açıkça dayanaktan
yoksun veya aşırı olmadıkça sizden ücret talep etmeyiz.

Bir şikâyeti yetkili denetim makamına iletebilirsiniz. ${country}'de bu makam
**Kişisel Verileri Koruma Kurumu (KVKK)**'dur. AEA'da ise ikamet ettiğiniz ülkenin
denetim makamıdır.

## 9. Güvenlik

Parolalar Argon2 ile özetlenir. Sağlayıcı API anahtarları, kod tabanının dışında
tutulan bir ana anahtar (master key) ile AES-256-GCM kullanılarak şifrelenir ve
tarayıcıya asla gönderilmez. Verilerinize ilişkin her sorgu, kullanıcı kimliğiniz
ile filtrelenir; böylece bir hesabın hafızası başka bir hesapta görünemez.
Ajanların çalıştırdığı kod, izole bir kum havuzunda (sandbox) yürütülür.

Ayrıntı için [Güvenlik sayfasını](/security) okuyun. Hiçbir sistem tümüyle
güvenli değildir; bir güvenlik açığı bulduğunuzu düşünüyorsanız ${contactEmail}
adresine yazın.

## 10. Otomatik Karar Verme

Hakkınızda hukuki veya benzer biçimde önemli sonuçlar doğuran kararları otomatik
yollarla vermeyiz. Ajanlar, talimatınız üzerine içerik üretir; hakkınızda herhangi
bir karar vermezler.

## 11. Çocuklar

Hizmet çocuklara yönelik değildir ve bilerek çocuklara ait veri toplamayız. Bir
çocuğun bize kişisel veri verdiğini düşünüyorsanız ${privacyEmail} adresine yazın;
veriyi silelim.

## 12. Değişiklikler

Bu metindeki esaslı değişiklikleri, yürürlüğe girmeden önce ürün içinde veya
e-posta yoluyla duyururuz. Sayfanın üst kısmındaki tarih her zaman güncel sürümü
yansıtır.

## 13. İletişim

Gizlilik ve ilgili kişi başvuruları: ${privacyEmail}
`.trim();
