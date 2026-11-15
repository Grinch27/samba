/* 待确认的关键需求：Win7 服务端的 SMB 方言与加密验收范围。
 * 歧义：加密原语通过只代表 DLL 能加载并执行相关运算。
 * 后续研究：在 Win7 SP1 上复测，随后验证实际协商的 SMB 方言与加密。
 * 潜在优化：仅在 smbd 集成后补测其他所需算法。
 * 风险：测试数据是固定向量，不能用于服务端密钥或随机数。
 * 验证重点：GnuTLS 初始化、HMAC-SHA256 与 AES-128-GCM 已知答案。
 */
#include <gnutls/crypto.h>
#include <gnutls/gnutls.h>
#include <stdio.h>
#include <string.h>
#include <sys/utsname.h>

int main(void)
{
    struct utsname runtime;
    if (uname(&runtime) != 0 || strncmp(runtime.release, "3.4.10-", 7) != 0) {
        fputs("Expected Cygwin 3.4.10.\n", stderr);
        return 2;
    }
    printf("Cygwin runtime: %s\n", runtime.release);
    const char *version = gnutls_check_version("3.6.13");
    if (version == NULL) {
        fputs("GnuTLS version is below Samba's minimum for getrandom.\n", stderr);
        return 1;
    }
    printf("GnuTLS runtime: %s\n", version);
    int result = gnutls_global_init();
    if (result < 0) {
        fprintf(stderr, "gnutls_global_init: %s\n", gnutls_strerror(result));
        return 1;
    }

    static const char message[] = "The quick brown fox jumps over the lazy dog";
    static const unsigned char expected_mac[] = {
        0xf7, 0xbc, 0x83, 0xf4, 0x30, 0x53, 0x84, 0x24, 0xb1, 0x32, 0x98, 0xe6, 0xaa, 0x6f, 0xb1, 0x43,
        0xef, 0x4d, 0x59, 0xa1, 0x49, 0x46, 0x17, 0x59, 0x97, 0x47, 0x9d, 0xbc, 0x2d, 0x1a, 0x3c, 0xd8,
    };
    unsigned char mac[sizeof(expected_mac)];
    result = gnutls_hmac_fast(GNUTLS_MAC_SHA256, "key", 3, message, sizeof(message) - 1, mac);
    if (result < 0 || memcmp(mac, expected_mac, sizeof(mac)) != 0) {
        fprintf(stderr, "HMAC-SHA256 known-answer test failed (GnuTLS status %d).\n", result);
        gnutls_global_deinit();
        return 1;
    }
    puts("HMAC-SHA256 known-answer test: PASS");

    unsigned char key[16] = {0};
    static const unsigned char nonce[12] = {0};
    static const unsigned char cleartext[16] = {0};
    static const unsigned char expected_ciphertext[] = {
        0x03, 0x88, 0xda, 0xce, 0x60, 0xb6, 0xa3, 0x92, 0xf3, 0x28, 0xc2, 0xb9, 0x71, 0xb2, 0xfe, 0x78,
        0xab, 0x6e, 0x47, 0xd4, 0x2c, 0xec, 0x13, 0xbd, 0xf5, 0x3a, 0x67, 0xb2, 0x12, 0x57, 0xbd, 0xdf,
    };
    unsigned char ciphertext[sizeof(expected_ciphertext)];
    size_t length = sizeof(ciphertext);
    const gnutls_datum_t secret = {key, sizeof(key)};
    gnutls_aead_cipher_hd_t cipher;
    result = gnutls_aead_cipher_init(&cipher, GNUTLS_CIPHER_AES_128_GCM, &secret);
    if (result >= 0) {
        result = gnutls_aead_cipher_encrypt(cipher, nonce, sizeof(nonce), NULL, 0, 16,
                                            cleartext, sizeof(cleartext), ciphertext, &length);
        gnutls_aead_cipher_deinit(cipher);
    }
    gnutls_global_deinit();
    if (result < 0 || length != sizeof(expected_ciphertext) ||
        memcmp(ciphertext, expected_ciphertext, sizeof(expected_ciphertext)) != 0) {
        fprintf(stderr, "AES-128-GCM known-answer test failed (GnuTLS status %d).\n", result);
        return 1;
    }
    puts("AES-128-GCM known-answer test: PASS");
    return 0;
}
