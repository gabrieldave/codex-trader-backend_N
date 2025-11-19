# Ejemplo de Componente de Bienvenida Modificado

Este archivo contiene el código de ejemplo para modificar la pantalla de bienvenida según tus requerimientos.

## Cambios Solicitados:
1. ✅ Quitar los mensajes/botones de sugerencias ("Puedes preguntarme sobre:")
2. ✅ Agregar mensaje: "Añade una imagen de tu gráfica para Análisis Profundo"
3. ✅ Botón llamativo y distinguido para subir imagen

## Código del Componente:

```tsx
import React, { useState, useRef } from 'react';
import Image from 'next/image'; // Si usas Next.js
// O usa <img> si es React normal

interface WelcomeScreenProps {
  onImageUpload?: (file: File) => void;
}

export default function WelcomeScreen({ onImageUpload }: WelcomeScreenProps) {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      // Mostrar preview
      const reader = new FileReader();
      reader.onloadend = () => {
        setSelectedImage(reader.result as string);
      };
      reader.readAsDataURL(file);
      
      // Llamar callback si existe
      if (onImageUpload) {
        onImageUpload(file);
      }
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-900 text-white p-4">
      {/* Título */}
      <div className="text-center mb-6">
        <h1 className="text-3xl font-bold mb-2">👋 Bienvenido a Codex Trader</h1>
        <p className="text-gray-300 text-sm max-w-md mx-auto">
          Tu asistente de IA especializado en trading, entrenado con contenido profesional de trading para ayudarte a entender mejor los mercados.
        </p>
      </div>

      {/* Mensaje principal sobre análisis profundo */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl p-6 mb-6 max-w-md w-full text-center shadow-2xl">
        <p className="text-white text-lg font-semibold mb-4">
          📊 Añade una imagen de tu gráfica para Análisis Profundo
        </p>
        
        {/* Botón llamativo para subir imagen */}
        <button
          onClick={handleButtonClick}
          className="w-full bg-yellow-400 hover:bg-yellow-500 text-gray-900 font-bold py-4 px-6 rounded-lg shadow-lg transform transition-all duration-200 hover:scale-105 active:scale-95 flex items-center justify-center gap-3"
          style={{
            boxShadow: '0 10px 25px rgba(250, 204, 21, 0.4)',
          }}
        >
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
          <span className="text-xl">Subir Gráfica</span>
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 7l5 5m0 0l-5 5m5-5H6"
            />
          </svg>
        </button>

        {/* Input oculto para subir archivo */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleImageSelect}
          className="hidden"
        />
      </div>

      {/* Preview de imagen si se selecciona */}
      {selectedImage && (
        <div className="mt-4 max-w-md w-full">
          <div className="bg-gray-800 rounded-lg p-4">
            <p className="text-gray-300 text-sm mb-2">Imagen seleccionada:</p>
            <img
              src={selectedImage}
              alt="Gráfica seleccionada"
              className="w-full rounded-lg border-2 border-yellow-400"
            />
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-gray-500 text-xs text-center mt-6 max-w-md">
        Codex usa contenido profesional de trading con fines educativos. No da recomendaciones personalizadas de inversión.
      </p>
    </div>
  );
}
```

## Versión con Tailwind CSS (Más Estilizada):

Si tu proyecto usa Tailwind CSS, aquí está una versión más estilizada:

```tsx
import React, { useState, useRef } from 'react';

export default function WelcomeScreen({ onImageUpload }: { onImageUpload?: (file: File) => void }) {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setSelectedImage(reader.result as string);
      };
      reader.readAsDataURL(file);
      
      if (onImageUpload) {
        onImageUpload(file);
      }
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4">
      {/* Título con animación */}
      <div className="text-center mb-8 animate-fade-in">
        <h1 className="text-4xl font-extrabold mb-3 bg-gradient-to-r from-yellow-400 to-orange-500 bg-clip-text text-transparent">
          👋 Bienvenido a Codex Trader
        </h1>
        <p className="text-gray-300 text-base max-w-md mx-auto leading-relaxed">
          Tu asistente de IA especializado en trading, entrenado con contenido profesional de trading para ayudarte a entender mejor los mercados.
        </p>
      </div>

      {/* Card principal con mensaje de análisis profundo */}
      <div className="bg-gradient-to-br from-blue-600 via-purple-600 to-pink-600 rounded-2xl p-8 mb-6 max-w-lg w-full text-center shadow-2xl transform transition-all duration-300 hover:scale-105">
        {/* Icono decorativo */}
        <div className="mb-4">
          <div className="w-20 h-20 mx-auto bg-white/20 rounded-full flex items-center justify-center backdrop-blur-sm">
            <svg
              className="w-10 h-10 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>
        </div>

        <p className="text-white text-xl font-bold mb-6">
          📊 Añade una imagen de tu gráfica para Análisis Profundo
        </p>
        
        {/* Botón SÚPER llamativo */}
        <button
          onClick={handleButtonClick}
          className="w-full bg-gradient-to-r from-yellow-400 via-yellow-500 to-orange-500 hover:from-yellow-500 hover:via-orange-500 hover:to-red-500 text-gray-900 font-extrabold py-5 px-8 rounded-xl shadow-2xl transform transition-all duration-300 hover:scale-110 active:scale-95 flex items-center justify-center gap-3 text-lg border-4 border-white/30"
          style={{
            boxShadow: '0 20px 40px rgba(250, 204, 21, 0.5), 0 0 20px rgba(250, 204, 21, 0.3)',
          }}
        >
          <svg
            className="w-7 h-7 animate-bounce"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
          <span className="text-xl">SUBIR GRÁFICA</span>
          <svg
            className="w-7 h-7"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3}
              d="M13 7l5 5m0 0l-5 5m5-5H6"
            />
          </svg>
        </button>

        {/* Input oculto */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleImageSelect}
          className="hidden"
        />
      </div>

      {/* Preview de imagen */}
      {selectedImage && (
        <div className="mt-6 max-w-lg w-full animate-fade-in">
          <div className="bg-gray-800/90 backdrop-blur-sm rounded-xl p-4 border-2 border-yellow-400/50">
            <p className="text-yellow-400 text-sm font-semibold mb-3 flex items-center gap-2">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              Imagen seleccionada
            </p>
            <img
              src={selectedImage}
              alt="Gráfica seleccionada"
              className="w-full rounded-lg border-2 border-yellow-400 shadow-lg"
            />
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-gray-400 text-xs text-center mt-8 max-w-md leading-relaxed">
        Codex usa contenido profesional de trading con fines educativos. No da recomendaciones personalizadas de inversión.
      </p>
    </div>
  );
}
```

## CSS Adicional (si no usas Tailwind):

```css
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fade-in 0.6s ease-out;
}

.animate-bounce {
  animation: bounce 1s infinite;
}
```

## Notas Importantes:

1. **Reemplaza el componente actual**: Busca el componente que muestra la pantalla de bienvenida (probablemente en `app/page.tsx`, `pages/index.tsx`, o un componente llamado `WelcomeScreen`, `HomeScreen`, etc.)

2. **Integra con tu lógica**: Asegúrate de que la función `onImageUpload` esté conectada con tu backend para enviar la imagen al endpoint de análisis profundo.

3. **Estilos**: Ajusta los estilos según tu tema actual (colores, fuentes, etc.)

4. **Responsive**: El código es responsive y debería funcionar bien en móvil y desktop.

## Para Integrar con el Backend:

```tsx
const handleImageUpload = async (file: File) => {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('query', 'Analiza esta gráfica en profundidad');
  
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      body: formData,
    });
    
    const data = await response.json();
    // Manejar la respuesta del análisis
  } catch (error) {
    console.error('Error al subir imagen:', error);
  }
};
```

