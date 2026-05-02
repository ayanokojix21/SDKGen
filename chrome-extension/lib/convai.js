import { Conversation } from '@elevenlabs/client';

class ConvAIController {
    constructor() {
        this.conversation = null;
        this.agentId = null;
    }

    setAgentId(id) {
        this.agentId = id;
    }

    async startConversation(onModeChange) {
        if (!this.agentId) {
            console.error("No agent ID set.");
            return;
        }

        try {
            // Request microphone access
            await navigator.mediaDevices.getUserMedia({ audio: true });

            // Start the session
            this.conversation = await Conversation.startSession({
                agentId: this.agentId, 
                onConnect: () => console.log('Connected to agent'),
                onDisconnect: () => console.log('Disconnected'),
                onError: (error) => console.error('Error:', error),
                onModeChange: (mode) => {
                    console.log('Agent is now:', mode.mode); // 'speaking' or 'listening'
                    if (onModeChange) onModeChange(mode.mode);
                }
            });
        } catch (error) {
            console.error('Failed to start conversation:', error);
            throw error;
        }
    }

    async stopConversation() {
        if (this.conversation) {
            await this.conversation.endSession();
            this.conversation = null;
        }
    }
}

window.convAi = new ConvAIController();
