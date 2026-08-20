# Vision Tracker V2 🎯

Um sistema modular de Visão Computacional e Telemetria focado em rastreamento de objetos em tempo real, desenvolvido com foco em performance e arquitetura de software limpa.

## 📌 Visão Geral
Este projeto implementa um pipeline de visão computacional capaz de capturar fluxos de vídeo (Câmera IP ou Local), aplicar processamento de imagem contínuo e extrair dados espaciais (centroides, trajetórias) de objetos específicos. O sistema é acoplado a um painel de telemetria assíncrono para monitoramento.

## 🏗️ Histórico e Motivação (Por que a V2?)
A **Versão 1** deste projeto consistia em uma arquitetura híbrida: o processamento de visão era feito em Python e os dados eram enviados via Sockets UDP para uma interface gráfica em Java. 

**Problemas identificados na V1:**
* **Overhead de Rede:** A comunicação inter-processos via UDP adicionava latência desnecessária ao loop de controle.
* **Complexidade de Manutenção:** Manter duas bases de código em linguagens diferentes e gerenciar a serialização dos pacotes violava o princípio de simplicidade para o escopo proposto.

A **Versão 2** resolve esse débito técnico ao unificar o ecossistema em **100% Python**. O processamento pesado continua sendo feito por bindings C++ (OpenCV/NumPy), mas a interface gráfica foi migrada para PySide6, permitindo o tráfego de matrizes de imagem via ponteiros de memória em vez de protocolos de rede.

## ⚙️ Arquitetura e Tecnologias
* **Linguagem:** Python 3
* **Visão Computacional:** OpenCV (`cv2`) + NumPy
* **Interface Gráfica (GUI):** PySide6
* **Design Patterns:** Orientação a Objetos, Segregação de Interfaces (IO de Vídeo isolado do Processamento Lógico).
* **Concorrência:** Uso de Multithreading (`QThread`) para evitar o bloqueio do Event Loop da interface pelo processamento síncrono dos quadros.

## 🚀 Roadmap e Escalabilidade (Próximos Passos)
Embora o escopo atual seja o rastreamento (scanner), a arquitetura modular permite rápida expansão para aplicações de robótica autônoma:

1. **Controle Cinemático:** Utilizar as coordenadas `(X, Y)` do objeto rastreado como *setpoints* para algoritmos de controle (ex: PID) para guiar o chassi de um robô.
2. **Comunicação Serial:** Integrar bibliotecas como `pyserial` para enviar os vetores de erro de trajetória diretamente para microcontroladores (Arduino/ESP32/STM32).
3. **Visão Estéreo/Profundidade:** Adicionar cálculos de distância (Eixo Z) baseados na área do contorno detectado, permitindo navegação em 3D.
4. **Integração ROS (Robot Operating System):** Empacotar o módulo de visão como um *ROS Node* publicador de tópicos de geometria espacial.

---
**Autor:** Mateus Augusto Guimarães  
**Estudante de Engenharia de Computação - UFG**