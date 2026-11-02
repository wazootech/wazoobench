/**
 * hash.ts implements the SPARQL 1.1 hash functions (MD5, SHA-1, SHA-256,
 * SHA-384, SHA-512) synchronously in pure TypeScript, so the expression
 * evaluator can call them without awaiting. SHA-1/SHA-256 use 32-bit word
 * arithmetic; SHA-384/SHA-512 use BigInt for the 64-bit words. All five
 * return lowercase hexadecimal strings of the digest.
 *
 * Prior art: the algorithms are the standard published message digests —
 * MD5 per IETF RFC 1321 and the SHA family per NIST FIPS 180-4 (which
 * SPARQL 1.1 §17.4.1.7 delegates to).
 * @see {@link https://www.rfc-editor.org/rfc/rfc1321 Rivest, "The MD5 Message-Digest Algorithm," IETF RFC 1321, 1992}
 * @see {@link https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf NIST, "Secure Hash Standard (SHS)," FIPS PUB 180-4, 2015}
 */

const MD5_S = [
  7,
  12,
  17,
  22,
  7,
  12,
  17,
  22,
  7,
  12,
  17,
  22,
  7,
  12,
  17,
  22,
  5,
  9,
  14,
  20,
  5,
  9,
  14,
  20,
  5,
  9,
  14,
  20,
  5,
  9,
  14,
  20,
  4,
  11,
  16,
  23,
  4,
  11,
  16,
  23,
  4,
  11,
  16,
  23,
  4,
  11,
  16,
  23,
  6,
  10,
  15,
  21,
  6,
  10,
  15,
  21,
  6,
  10,
  15,
  21,
  6,
  10,
  15,
  21,
];

/**
 * MD5_K holds the 64 round constants, defined as floor(|sin(i+1)| * 2^32).
 */
const MD5_K: number[] = Array.from(
  { length: 64 },
  (_, index) => Math.floor(Math.abs(Math.sin(index + 1)) * 0x100000000),
);

/**
 * md5Hex returns the MD5 digest of the UTF-8 encoding of the input as
 * lowercase hexadecimal.
 */
export function md5Hex(input: string): string {
  const bytes = new TextEncoder().encode(input);
  const bitLength = bytes.length * 8;
  const paddedLength = (((bytes.length + 8) >> 6) + 1) << 6;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  // 64-bit little-endian message length in bits.
  view.setUint32(paddedLength - 8, bitLength >>> 0, true);
  view.setUint32(paddedLength - 4, Math.floor(bitLength / 0x100000000), true);

  let a0 = 0x67452301;
  let b0 = 0xefcdab89;
  let c0 = 0x98badcfe;
  let d0 = 0x10325476;

  for (let offset = 0; offset < paddedLength; offset += 64) {
    const m = new Array<number>(16);
    for (let index = 0; index < 16; index++) {
      m[index] = view.getUint32(offset + index * 4, true);
    }
    let a = a0;
    let b = b0;
    let c = c0;
    let d = d0;
    for (let index = 0; index < 64; index++) {
      let f: number;
      let g: number;
      if (index < 16) {
        f = (b & c) | (~b & d);
        g = index;
      } else if (index < 32) {
        f = (d & b) | (~d & c);
        g = (5 * index + 1) % 16;
      } else if (index < 48) {
        f = b ^ c ^ d;
        g = (3 * index + 5) % 16;
      } else {
        f = c ^ (b | ~d);
        g = (7 * index) % 16;
      }
      f = (f + a + MD5_K[index] + m[g]) >>> 0;
      a = d;
      d = c;
      c = b;
      b = (b + ((f << MD5_S[index]) | (f >>> (32 - MD5_S[index])))) >>> 0;
    }
    a0 = (a0 + a) >>> 0;
    b0 = (b0 + b) >>> 0;
    c0 = (c0 + c) >>> 0;
    d0 = (d0 + d) >>> 0;
  }

  // MD5 digests the words in little-endian byte order.
  const wordHex = (word: number): string => {
    let result = "";
    for (let byte = 0; byte < 4; byte++) {
      result += ((word >>> (byte * 8)) & 0xff).toString(16).padStart(2, "0");
    }
    return result;
  };
  return wordHex(a0) + wordHex(b0) + wordHex(c0) + wordHex(d0);
}

/**
 * sha1Hex returns the SHA-1 digest of the UTF-8 encoding of the input as
 * lowercase hexadecimal.
 */
export function sha1Hex(input: string): string {
  const bytes = new TextEncoder().encode(input);
  const bitLength = bytes.length * 8;
  const paddedLength = (((bytes.length + 8) >> 6) + 1) << 6;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  // 64-bit big-endian message length in bits.
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);

  let h0 = 0x67452301;
  let h1 = 0xefcdab89;
  let h2 = 0x98badcfe;
  let h3 = 0x10325476;
  let h4 = 0xc3d2e1f0;

  const rotateLeft = (value: number, bits: number): number =>
    ((value << bits) | (value >>> (32 - bits))) >>> 0;

  for (let offset = 0; offset < paddedLength; offset += 64) {
    const w = new Array<number>(80);
    for (let index = 0; index < 16; index++) {
      w[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 80; index++) {
      w[index] = rotateLeft(
        w[index - 3] ^ w[index - 8] ^ w[index - 14] ^ w[index - 16],
        1,
      );
    }
    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    for (let index = 0; index < 80; index++) {
      let f: number;
      let k: number;
      if (index < 20) {
        f = (b & c) | (~b & d);
        k = 0x5a827999;
      } else if (index < 40) {
        f = b ^ c ^ d;
        k = 0x6ed9eba1;
      } else if (index < 60) {
        f = (b & c) | (b & d) | (c & d);
        k = 0x8f1bbcdc;
      } else {
        f = b ^ c ^ d;
        k = 0xca62c1d6;
      }
      const temp = (rotateLeft(a, 5) + f + e + k + w[index]) >>> 0;
      e = d;
      d = c;
      c = rotateLeft(b, 30);
      b = a;
      a = temp;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
  }

  const wordHex = (word: number): string => word.toString(16).padStart(8, "0");
  return wordHex(h0) + wordHex(h1) + wordHex(h2) + wordHex(h3) +
    wordHex(h4);
}

const SHA256_K = [
  0x428a2f98,
  0x71374491,
  0xb5c0fbcf,
  0xe9b5dba5,
  0x3956c25b,
  0x59f111f1,
  0x923f82a4,
  0xab1c5ed5,
  0xd807aa98,
  0x12835b01,
  0x243185be,
  0x550c7dc3,
  0x72be5d74,
  0x80deb1fe,
  0x9bdc06a7,
  0xc19bf174,
  0xe49b69c1,
  0xefbe4786,
  0x0fc19dc6,
  0x240ca1cc,
  0x2de92c6f,
  0x4a7484aa,
  0x5cb0a9dc,
  0x76f988da,
  0x983e5152,
  0xa831c66d,
  0xb00327c8,
  0xbf597fc7,
  0xc6e00bf3,
  0xd5a79147,
  0x06ca6351,
  0x14292967,
  0x27b70a85,
  0x2e1b2138,
  0x4d2c6dfc,
  0x53380d13,
  0x650a7354,
  0x766a0abb,
  0x81c2c92e,
  0x92722c85,
  0xa2bfe8a1,
  0xa81a664b,
  0xc24b8b70,
  0xc76c51a3,
  0xd192e819,
  0xd6990624,
  0xf40e3585,
  0x106aa070,
  0x19a4c116,
  0x1e376c08,
  0x2748774c,
  0x34b0bcb5,
  0x391c0cb3,
  0x4ed8aa4a,
  0x5b9cca4f,
  0x682e6ff3,
  0x748f82ee,
  0x78a5636f,
  0x84c87814,
  0x8cc70208,
  0x90befffa,
  0xa4506ceb,
  0xbef9a3f7,
  0xc67178f2,
];

/**
 * sha256Hex returns the SHA-256 digest of the UTF-8 encoding of the input as
 * lowercase hexadecimal.
 */
export function sha256Hex(input: string): string {
  const bytes = new TextEncoder().encode(input);
  const bitLength = bytes.length * 8;
  const paddedLength = (((bytes.length + 8) >> 6) + 1) << 6;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);

  let h0 = 0x6a09e667;
  let h1 = 0xbb67ae85;
  let h2 = 0x3c6ef372;
  let h3 = 0xa54ff53a;
  let h4 = 0x510e527f;
  let h5 = 0x9b05688c;
  let h6 = 0x1f83d9ab;
  let h7 = 0x5be0cd19;

  const rotateRight = (value: number, bits: number): number =>
    ((value >>> bits) | (value << (32 - bits))) >>> 0;

  for (let offset = 0; offset < paddedLength; offset += 64) {
    const w = new Array<number>(64);
    for (let index = 0; index < 16; index++) {
      w[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 64; index++) {
      const s0 = rotateRight(w[index - 15], 7) ^
        rotateRight(w[index - 15], 18) ^ (w[index - 15] >>> 3);
      const s1 = rotateRight(w[index - 2], 17) ^
        rotateRight(w[index - 2], 19) ^ (w[index - 2] >>> 10);
      w[index] = (w[index - 16] + s0 + w[index - 7] + s1) >>> 0;
    }
    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    let f = h5;
    let g = h6;
    let h = h7;
    for (let index = 0; index < 64; index++) {
      const s1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^
        rotateRight(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + SHA256_K[index] + w[index]) >>> 0;
      const s0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^
        rotateRight(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
    h5 = (h5 + f) >>> 0;
    h6 = (h6 + g) >>> 0;
    h7 = (h7 + h) >>> 0;
  }

  const wordHex = (word: number): string => word.toString(16).padStart(8, "0");
  return wordHex(h0) + wordHex(h1) + wordHex(h2) + wordHex(h3) +
    wordHex(h4) + wordHex(h5) + wordHex(h6) + wordHex(h7);
}

const MASK64 = 0xffffffffffffffffn;

const rotateRight64 = (value: bigint, bits: bigint): bigint =>
  ((value >> bits) | (value << (64n - bits))) & MASK64;

const SHA512_K: bigint[] = [
  0x428a2f98d728ae22n,
  0x7137449123ef65cdn,
  0xb5c0fbcfec4d3b2fn,
  0xe9b5dba58189dbbcn,
  0x3956c25bf348b538n,
  0x59f111f1b605d019n,
  0x923f82a4af194f9bn,
  0xab1c5ed5da6d8118n,
  0xd807aa98a3030242n,
  0x12835b0145706fben,
  0x243185be4ee4b28cn,
  0x550c7dc3d5ffb4e2n,
  0x72be5d74f27b896fn,
  0x80deb1fe3b1696b1n,
  0x9bdc06a725c71235n,
  0xc19bf174cf692694n,
  0xe49b69c19ef14ad2n,
  0xefbe4786384f25e3n,
  0x0fc19dc68b8cd5b5n,
  0x240ca1cc77ac9c65n,
  0x2de92c6f592b0275n,
  0x4a7484aa6ea6e483n,
  0x5cb0a9dcbd41fbd4n,
  0x76f988da831153b5n,
  0x983e5152ee66dfabn,
  0xa831c66d2db43210n,
  0xb00327c898fb213fn,
  0xbf597fc7beef0ee4n,
  0xc6e00bf33da88fc2n,
  0xd5a79147930aa725n,
  0x06ca6351e003826fn,
  0x142929670a0e6e70n,
  0x27b70a8546d22ffcn,
  0x2e1b21385c26c926n,
  0x4d2c6dfc5ac42aedn,
  0x53380d139d95b3dfn,
  0x650a73548baf63den,
  0x766a0abb3c77b2a8n,
  0x81c2c92e47edaee6n,
  0x92722c851482353bn,
  0xa2bfe8a14cf10364n,
  0xa81a664bbc423001n,
  0xc24b8b70d0f89791n,
  0xc76c51a30654be30n,
  0xd192e819d6ef5218n,
  0xd69906245565a910n,
  0xf40e35855771202an,
  0x106aa07032bbd1b8n,
  0x19a4c116b8d2d0c8n,
  0x1e376c085141ab53n,
  0x2748774cdf8eeb99n,
  0x34b0bcb5e19b48a8n,
  0x391c0cb3c5c95a63n,
  0x4ed8aa4ae3418acbn,
  0x5b9cca4f7763e373n,
  0x682e6ff3d6b2b8a3n,
  0x748f82ee5defb2fcn,
  0x78a5636f43172f60n,
  0x84c87814a1f0ab72n,
  0x8cc702081a6439ecn,
  0x90befffa23631e28n,
  0xa4506cebde82bde9n,
  0xbef9a3f7b2c67915n,
  0xc67178f2e372532bn,
  0xca273eceea26619cn,
  0xd186b8c721c0c207n,
  0xeada7dd6cde0eb1en,
  0xf57d4f7fee6ed178n,
  0x06f067aa72176fban,
  0x0a637dc5a2c898a6n,
  0x113f9804bef90daen,
  0x1b710b35131c471bn,
  0x28db77f523047d84n,
  0x32caab7b40c72493n,
  0x3c9ebe0a15c9bebcn,
  0x431d67c49c100d4cn,
  0x4cc5d4becb3e42b6n,
  0x597f299cfc657e2an,
  0x5fcb6fab3ad6faecn,
  0x6c44198c4a475817n,
];

/**
 * sha512Digest runs the SHA-512 compression over the input with the given
 * initial hash values, returning the 8 state words (or a prefix of them for
 * SHA-384).
 */
function sha512Words(
  input: string,
  initial: bigint[],
): bigint[] {
  const bytes = new TextEncoder().encode(input);
  const bitLength = BigInt(bytes.length * 8);
  const paddedLength = (((bytes.length + 16) >> 7) + 1) << 7;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  // 128-bit big-endian message length in bits.
  view.setBigUint64(paddedLength - 16, bitLength >> 64n, false);
  view.setBigUint64(paddedLength - 8, bitLength & MASK64, false);

  let state = [...initial];
  for (let offset = 0; offset < paddedLength; offset += 128) {
    const w = new Array<bigint>(80);
    for (let index = 0; index < 16; index++) {
      w[index] = view.getBigUint64(offset + index * 8, false);
    }
    for (let index = 16; index < 80; index++) {
      const s0 = rotateRight64(w[index - 15], 1n) ^
        rotateRight64(w[index - 15], 8n) ^ (w[index - 15] >> 7n);
      const s1 = rotateRight64(w[index - 2], 19n) ^
        rotateRight64(w[index - 2], 61n) ^ (w[index - 2] >> 6n);
      w[index] = (w[index - 16] + s0 + w[index - 7] + s1) & MASK64;
    }
    let [a, b, c, d, e, f, g, h] = state;
    for (let index = 0; index < 80; index++) {
      const s1 = rotateRight64(e, 14n) ^ rotateRight64(e, 18n) ^
        rotateRight64(e, 41n);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + SHA512_K[index] + w[index]) & MASK64;
      const s0 = rotateRight64(a, 28n) ^ rotateRight64(a, 34n) ^
        rotateRight64(a, 39n);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) & MASK64;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) & MASK64;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) & MASK64;
    }
    state = [
      (a + state[0]) & MASK64,
      (b + state[1]) & MASK64,
      (c + state[2]) & MASK64,
      (d + state[3]) & MASK64,
      (e + state[4]) & MASK64,
      (f + state[5]) & MASK64,
      (g + state[6]) & MASK64,
      (h + state[7]) & MASK64,
    ];
  }
  return state;
}

const SHA512_IV = [
  0x6a09e667f3bcc908n,
  0xbb67ae8584caa73bn,
  0x3c6ef372fe94f82bn,
  0xa54ff53a5f1d36f1n,
  0x510e527fade682d1n,
  0x9b05688c2b3e6c1fn,
  0x1f83d9abfb41bd6bn,
  0x5be0cd19137e2179n,
];

const SHA384_IV = [
  0xcbbb9d5dc1059ed8n,
  0x629a292a367cd507n,
  0x9159015a3070dd17n,
  0x152fecd8f70e5939n,
  0x67332667ffc00b31n,
  0x8eb44a8768581511n,
  0xdb0c2e0d64f98fa7n,
  0x47b5481dbefa4fa4n,
];

const word64Hex = (word: bigint): string => word.toString(16).padStart(16, "0");

/**
 * sha384Hex returns the SHA-384 digest of the UTF-8 encoding of the input as
 * lowercase hexadecimal.
 */
export function sha384Hex(input: string): string {
  return sha512Words(input, SHA384_IV).slice(0, 6).map(word64Hex).join("");
}

/**
 * sha512Hex returns the SHA-512 digest of the UTF-8 encoding of the input as
 * lowercase hexadecimal.
 */
export function sha512Hex(input: string): string {
  return sha512Words(input, SHA512_IV).map(word64Hex).join("");
}
