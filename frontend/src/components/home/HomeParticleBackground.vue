<template>
  <div class="particle-background" aria-hidden="true">
    <canvas
      ref="canvasRef"
      class="wave-canvas"
      :class="{ 'wave-canvas--ready': rendererReady }"
    ></canvas>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

const canvasRef = ref(null);
const rendererReady = ref(false);

const LOOP_DURATION_SECONDS = 20;
const vertexShaderSource = `
  attribute vec2 a_position;
  varying vec2 v_uv;

  void main() {
    v_uv = a_position * 0.5 + 0.5;
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`;

const fragmentShaderSource = `
  precision highp float;

  uniform vec2 u_resolution;
  uniform float u_time;
  varying vec2 v_uv;

  const float PI = 3.141592653589793;
  const float LOOP_SECONDS = 20.0;

  float hash21(vec2 point) {
    point = fract(point * vec2(123.34, 456.21));
    point += dot(point, point + 45.32);
    return fract(point.x * point.y);
  }

  float valueNoise(vec2 point) {
    vec2 cell = floor(point);
    vec2 local = fract(point);
    local = local * local * (3.0 - 2.0 * local);

    float lowerLeft = hash21(cell);
    float lowerRight = hash21(cell + vec2(1.0, 0.0));
    float upperLeft = hash21(cell + vec2(0.0, 1.0));
    float upperRight = hash21(cell + vec2(1.0, 1.0));

    return mix(
      mix(lowerLeft, lowerRight, local.x),
      mix(upperLeft, upperRight, local.x),
      local.y
    );
  }

  float flowNoise(vec2 point) {
    float value = 0.0;
    float amplitude = 0.56;
    mat2 rotation = mat2(0.82, -0.57, 0.57, 0.82);

    for (int index = 0; index < 3; index++) {
      value += valueNoise(point) * amplitude;
      point = rotation * point * 2.03 + vec2(1.7, -2.1);
      amplitude *= 0.48;
    }

    return value;
  }

  void main() {
    vec2 uv = v_uv;
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    float phase = u_time / LOOP_SECONDS * PI * 2.0;
    vec2 loopOffset = vec2(cos(phase), sin(phase));
    vec2 perpendicularOffset = vec2(-loopOffset.y, loopOffset.x);
    vec2 aspectUv = vec2(uv.x * aspect, uv.y);

    float broadFlow = flowNoise(aspectUv * 1.24 + loopOffset * 0.52);
    float secondaryFlow = flowNoise(aspectUv * 2.34 + perpendicularOffset * 0.7);

    float waveLine =
      0.36
      + sin(uv.x * 3.1 + phase) * 0.068
      + sin(uv.x * 7.4 - phase * 2.0) * 0.032
      + (broadFlow - 0.5) * 0.24
      + (secondaryFlow - 0.5) * 0.066;

    float waveBody = 1.0 - smoothstep(waveLine - 0.25, waveLine + 0.28, uv.y);
    float lowerCurrent =
      1.0
      - smoothstep(
        0.2 + sin(uv.x * 4.6 - phase) * 0.07,
        0.56 + sin(uv.x * 2.4 + phase * 2.0) * 0.05,
        uv.y
      );
    float blueAmount = clamp(waveBody * 0.92 + lowerCurrent * 0.2, 0.0, 1.0);

    vec3 lightColor = vec3(0.985, 0.993, 1.0);
    vec3 frostColor = vec3(0.87, 0.965, 1.0);
    vec3 mistColor = vec3(0.68, 0.9, 0.99);
    vec3 cyanColor = vec3(0.34, 0.79, 0.975);
    vec3 skyColor = vec3(0.11, 0.63, 0.95);
    vec3 lowerBlueColor = vec3(0.055, 0.52, 0.91);
    vec3 ridgeBlueColor = vec3(0.045, 0.34, 0.83);

    float palettePosition = clamp(
      blueAmount
      + (broadFlow - 0.5) * 0.065
      + (secondaryFlow - 0.5) * 0.038,
      0.0,
      1.0
    );

    vec3 color = mix(lightColor, frostColor, smoothstep(0.0, 0.32, palettePosition));
    color = mix(color, mistColor, smoothstep(0.14, 0.5, palettePosition));
    color = mix(color, cyanColor, smoothstep(0.31, 0.7, palettePosition));
    color = mix(color, skyColor, smoothstep(0.5, 0.87, palettePosition));
    color = mix(color, lowerBlueColor, smoothstep(0.73, 1.0, palettePosition));

    float ridgeCenter = 0.72 + (secondaryFlow - 0.5) * 0.06;
    float ridgeDistance = abs(palettePosition - ridgeCenter);
    float darkRidge = 1.0 - smoothstep(0.075, 0.235, ridgeDistance);
    darkRidge *= smoothstep(0.34, 0.68, blueAmount);
    darkRidge *= 1.0 - smoothstep(0.9, 1.0, blueAmount);
    color = mix(color, ridgeBlueColor, darkRidge * 0.58);

    float ribbonLine =
      waveLine
      - 0.17
      + sin(uv.x * 4.2 + phase * 2.0) * 0.035
      + (secondaryFlow - 0.5) * 0.07;
    float ribbonDistance = abs(uv.y - ribbonLine);
    float lightRibbon = 1.0 - smoothstep(0.014, 0.066, ribbonDistance);
    float ribbonTravel = 0.5 + 0.5 * sin(uv.x * 2.8 - phase);
    float ribbonPulse = 0.5 + 0.5 * sin(phase - 0.7);
    float ribbonVisibility =
      smoothstep(0.16, 0.88, ribbonTravel)
      * mix(0.26, 1.0, ribbonPulse);
    lightRibbon *= ribbonVisibility * smoothstep(0.28, 0.76, blueAmount);
    color = mix(color, mistColor, lightRibbon * 0.34);

    vec2 grainFlow = loopOffset * 28.0 + perpendicularOffset * 9.0;
    float fineGrain = valueNoise(gl_FragCoord.xy / 2.2 + grainFlow);
    float microGrain = valueNoise(gl_FragCoord.xy / 1.08 - grainFlow * 0.55);
    float grain = mix(fineGrain, microGrain, 0.46);
    float grainStrength = mix(0.012, 0.078, smoothstep(0.16, 0.96, blueAmount));

    color += (grain - 0.5) * grainStrength;
    color += vec3(-0.035, 0.006, 0.038) * (secondaryFlow - 0.5) * blueAmount;

    float topLight = smoothstep(0.6, 1.0, uv.y);
    color = mix(color, lightColor, topLight * 0.08);

    gl_FragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
  }
`;

let gl = null;
let program = null;
let positionBuffer = null;
let positionLocation = -1;
let resolutionLocation = null;
let timeLocation = null;
let animationFrame = 0;
let animationStartTime = null;
let reduceMotion = false;

function compileShader(type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);

  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(message || "背景着色器编译失败");
  }

  return shader;
}

function createProgram() {
  const vertexShader = compileShader(gl.VERTEX_SHADER, vertexShaderSource);
  const fragmentShader = compileShader(gl.FRAGMENT_SHADER, fragmentShaderSource);
  const nextProgram = gl.createProgram();

  gl.attachShader(nextProgram, vertexShader);
  gl.attachShader(nextProgram, fragmentShader);
  gl.linkProgram(nextProgram);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);

  if (!gl.getProgramParameter(nextProgram, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(nextProgram);
    gl.deleteProgram(nextProgram);
    throw new Error(message || "背景渲染程序链接失败");
  }

  return nextProgram;
}

function resizeCanvas() {
  const canvas = canvasRef.value;
  if (!canvas || !gl) return;

  const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
  const width = Math.max(1, Math.round(window.innerWidth * pixelRatio));
  const height = Math.max(1, Math.round(window.innerHeight * pixelRatio));

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
    gl.viewport(0, 0, width, height);
  }
}

function drawFrame(timestamp = 0) {
  if (!gl || !program) return;

  resizeCanvas();
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.enableVertexAttribArray(positionLocation);
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
  gl.uniform2f(resolutionLocation, gl.drawingBufferWidth, gl.drawingBufferHeight);
  gl.uniform1f(
    timeLocation,
    reduceMotion ? LOOP_DURATION_SECONDS * 0.18 : timestamp / 1000,
  );
  gl.drawArrays(gl.TRIANGLES, 0, 6);
}

function animate(timestamp) {
  if (animationStartTime === null) {
    animationStartTime = timestamp;
  }
  drawFrame(timestamp - animationStartTime);
  animationFrame = window.requestAnimationFrame(animate);
}

function initializeRenderer() {
  const canvas = canvasRef.value;
  if (!canvas) return;

  gl = canvas.getContext("webgl", {
    alpha: false,
    antialias: false,
    depth: false,
    powerPreference: "high-performance",
    preserveDrawingBuffer: false,
  });

  if (!gl) return;

  program = createProgram();
  positionBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.bufferData(
    gl.ARRAY_BUFFER,
    new Float32Array([
      -1, -1,
      1, -1,
      -1, 1,
      -1, 1,
      1, -1,
      1, 1,
    ]),
    gl.STATIC_DRAW,
  );

  positionLocation = gl.getAttribLocation(program, "a_position");
  resolutionLocation = gl.getUniformLocation(program, "u_resolution");
  timeLocation = gl.getUniformLocation(program, "u_time");
  resizeCanvas();
  drawFrame();
  rendererReady.value = true;

  if (!reduceMotion) {
    animationFrame = window.requestAnimationFrame(animate);
  }
}

function handleVisibilityChange() {
  window.cancelAnimationFrame(animationFrame);
  if (document.hidden || reduceMotion) {
    drawFrame();
    return;
  }
  animationFrame = window.requestAnimationFrame(animate);
}

function handleContextLost(event) {
  event.preventDefault();
  window.cancelAnimationFrame(animationFrame);
  rendererReady.value = false;
}

function handleContextRestored() {
  initializeRenderer();
}

onMounted(() => {
  reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  try {
    initializeRenderer();
  } catch (error) {
    console.warn("动态波浪背景初始化失败，已使用静态渐变。", error);
  }

  window.addEventListener("resize", resizeCanvas, { passive: true });
  document.addEventListener("visibilitychange", handleVisibilityChange);
  canvasRef.value?.addEventListener("webglcontextlost", handleContextLost);
  canvasRef.value?.addEventListener("webglcontextrestored", handleContextRestored);
});

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrame);
  window.removeEventListener("resize", resizeCanvas);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  canvasRef.value?.removeEventListener("webglcontextlost", handleContextLost);
  canvasRef.value?.removeEventListener("webglcontextrestored", handleContextRestored);

  if (gl) {
    if (positionBuffer) gl.deleteBuffer(positionBuffer);
    if (program) gl.deleteProgram(program);
  }
});
</script>

<style scoped>
.particle-background {
  position: fixed;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
  inset: 0;
  background:
    radial-gradient(ellipse 72% 44% at 48% 14%, #ffffff 0 38%, rgba(246, 251, 255, 0.9) 64%, transparent 100%),
    linear-gradient(168deg, #ffffff 0%, #f8fcff 30%, #c9efff 52%, #3fa8ef 76%, #1454ca 100%);
}

.wave-canvas {
  display: block;
  width: 100%;
  height: 100%;
  opacity: 0;
  transition: opacity 0.45s ease;
}

.wave-canvas--ready {
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .wave-canvas {
    transition: none;
  }
}
</style>
