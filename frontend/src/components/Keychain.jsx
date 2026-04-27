import { Canvas } from '@react-three/fiber';
import { useGLTF, Float, PresentationControls, Environment } from '@react-three/drei';
import { Suspense } from 'react';

function Model() {
  // credit: "Hello Kitty Keychain 3D Model" (https://skfb.ly/pC8JP) by Gothic_404 is licensed under Creative Commons Attribution (http://creativecommons.org/licenses/by/4.0/). 
  const { scene } = useGLTF('/hello_kitty_keychain_3d_model.glb');
  // Ensure materials are visible and reflective
  scene.traverse((child) => {
    if (child.isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });
  return <primitive object={scene} scale={8} position={[0, -6, 0]}/>;
}

const Keychain = () => {
  return (
    <div style={{ width: '100%', height: '100%', background: 'transparent' }}>
      <Canvas 
        dpr={[1, 2]} 
        camera={{ fov: 40, position: [0, 0, 30], near: 0.1, far: 1000 }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={4} />
        <pointLight position={[20, 20, 20]} intensity={3} />
        <pointLight position={[-20, -20, 15]} intensity={2.5} />
        <pointLight position={[0, 0, 25]} intensity={3} />
        <pointLight position={[20, -20, 20]} intensity={2} />
        <directionalLight position={[10, 10, 10]} intensity={2} />
        <Environment preset="studio" intensity={1.5} />
        <Suspense fallback={null}>
          <Float speed={0.5} rotationIntensity={0.3} floatIntensity={0.3}>
            <PresentationControls 
              global 
              config={{ mass: 2, tension: 400 }}
              rotation={[0, 0, 0]} 
              polar={[-Math.PI, Math.PI]} 
              azimuth={[-Math.PI, Math.PI]}
            >
              <Model />
            </PresentationControls>
          </Float>
        </Suspense>
      </Canvas>
    </div>
  );
};

export default Keychain;