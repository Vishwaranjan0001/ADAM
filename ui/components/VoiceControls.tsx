'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { transcribeAudio, synthesizeSpeech } from '@/lib/api';
import { Mic, MicOff, Volume2, VolumeX, Square, Play, Loader2 } from 'lucide-react';

interface VoiceControlsProps {
  onTranscript: (text: string) => void;
  ttsText: string;
  ttsEnabled: boolean;
  onToggleTts: () => void;
  language?: string;
}

export default function VoiceControls({
  onTranscript,
  ttsText,
  ttsEnabled,
  onToggleTts,
  language = 'hi',
}: VoiceControlsProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recordingRef = useRef(false);
  const lastSpokenTextRef = useRef('');

  const speakWithBrowser = useCallback((text: string) => {
    if (!('speechSynthesis' in window)) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language === 'hi' ? 'hi-IN' : 'en-IN';
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
    return true;
  }, [language]);

  const startRecording = useCallback(async () => {
    if (recordingRef.current) return;
    try {
      recordingRef.current = true;
      setVoiceError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setIsTranscribing(true);
        try {
          const result = await transcribeAudio(blob, language);
          onTranscript(result.transcript);
        } catch (err) {
          console.error('Transcription failed:', err);
          setVoiceError(err instanceof Error ? err.message : 'Speech-to-text is unavailable.');
        } finally {
          setIsTranscribing(false);
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) {
      recordingRef.current = false;
      console.error('Microphone access denied:', err);
    }
  }, [language, onTranscript]);

  const stopRecording = useCallback(() => {
    if (!recordingRef.current) return;
    recordingRef.current = false;
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }, []);

  const speakText = useCallback(async () => {
    if (!ttsText || isSpeaking) return;
    setIsSpeaking(true);
    try {
      const blob = await synthesizeSpeech(ttsText, language);
      // The backend deliberately uses a 44-byte silent WAV when Piper is not
      // installed.  Use the browser's local speech engine in that case.
      if (blob.size <= 44 && speakWithBrowser(ttsText)) return;
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setIsSpeaking(false);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setIsSpeaking(false);
      };
      await audio.play();
    } catch (err) {
      console.error('TTS failed:', err);
      if (!speakWithBrowser(ttsText)) setIsSpeaking(false);
    }
  }, [ttsText, language, isSpeaking, speakWithBrowser]);

  const stopSpeaking = useCallback(() => {
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
  }, []);

  // With voice output enabled, a spoken prompt completes the STT → chat → TTS
  // loop without requiring a second click.  Text answers are read the same way.
  useEffect(() => {
    if (ttsEnabled && ttsText && ttsText !== lastSpokenTextRef.current && !isSpeaking) {
      lastSpokenTextRef.current = ttsText;
      void speakText();
    }
  }, [ttsEnabled, ttsText, isSpeaking, speakText]);

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        {/* Mic Button */}
        <button
        type="button"
        onPointerDown={startRecording}
        onPointerUp={stopRecording}
        onPointerCancel={stopRecording}
        disabled={isTranscribing}
        title={isRecording ? 'Recording… release to transcribe' : 'Hold to speak voice input'}
        className={`p-2 rounded-xl transition-all ${
          isRecording
            ? 'bg-rose-500 text-white shadow-sm animate-pulse'
            : isTranscribing
            ? 'bg-gray-100 text-gray-400 cursor-wait'
            : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
        }`}
      >
        {isTranscribing ? (
          <Loader2 className="w-4 h-4 animate-spin text-purple-600" />
        ) : isRecording ? (
          <MicOff className="w-4 h-4" />
        ) : (
          <Mic className="w-4 h-4" />
        )}
        </button>

        {/* Speaker Toggle Button */}
        <button
        type="button"
        onClick={onToggleTts}
        title={ttsEnabled ? 'Voice output enabled' : 'Enable voice output'}
        className={`p-2 rounded-xl transition-all ${
          ttsEnabled
            ? 'text-purple-600 bg-purple-50/80'
            : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
        }`}
      >
        {ttsEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
        </button>

        {/* Read aloud / Stop speaking when TTS enabled & text available */}
        {ttsEnabled && ttsText && (
          <button
          type="button"
          onClick={isSpeaking ? stopSpeaking : speakText}
          title={isSpeaking ? 'Stop reading' : 'Read answer aloud'}
          className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200/60 transition-colors"
        >
          {isSpeaking ? (
            <>
              <Square className="w-3 h-3 fill-current" />
              <span>Stop</span>
            </>
          ) : (
            <>
              <Play className="w-3 h-3 fill-current" />
              <span>Listen</span>
            </>
          )}
          </button>
        )}
      </div>
      {voiceError && (
        <p role="alert" className="max-w-64 text-right text-[10px] leading-tight text-rose-600">
          {voiceError}
        </p>
      )}
    </div>
  );
}
