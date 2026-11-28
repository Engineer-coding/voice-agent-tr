// Mikrofon sesini 16 kHz, 16 bit PCM'e çevirip ~20 ms'lik parçalar halinde ana iş parçacığına yollar.
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0; // kaynak örnek konumu (kesirli)
    this.acc = 0;
    this.count = 0;
    this.out = new Int16Array(320);
    this.outLen = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      // Basit kutu filtre: her çıkış örneği, karşılık gelen giriş örneklerinin ortalaması.
      this.acc += channel[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.acc / this.count));
        this.out[this.outLen++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        this.acc = 0;
        this.count = 0;
        if (this.outLen === this.out.length) {
          this.port.postMessage(this.out.buffer.slice(0));
          this.outLen = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
