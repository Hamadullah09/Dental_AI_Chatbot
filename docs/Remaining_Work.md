# Remaining Work for Dental AI Chatbot

## 1. User Management and Authentication

Implement authentication using JWT or OAuth to manage user and admin roles. Users should have secure sessions and chat history tied to their accounts.  Admin panel should allow uploading new dental documents and monitoring usage.

## 2. Document Upload and Ingestion

Develop endpoints and a UI for administrators to upload PDF documents directly from the web interface.  Upon upload, automatically run the ingestion process to add the document to the vector database.

## 3. Chat History and Database Integration

Integrate a relational database (PostgreSQL) to store user profiles, chat sessions, and messages.  Use this data to provide context‑aware responses and for auditing.  Ensure sensitive information is protected and comply with healthcare data regulations.

## 4. Evaluation and Safety Checks

Integrate the llm‑evaluation‑for‑dentistry toolkit to assess answer quality and safety.  Implement a feedback loop to flag responses that may contain hallucinations or unsafe recommendations.  Continuously improve prompts and retrieval strategies based on evaluation results.

## 5. Advanced Features

Consider integrating oral image analysis models (e.g., DentalGPT, OralGPT) to support multimodal queries in the future.  Implement follow‑up question suggestions, interactive learning modes for students, and patient‑specific guidance with explicit consent.

## 6. Deployment and Monitoring

Dockerize the application for easier deployment to cloud platforms like AWS or Azure.  Set up monitoring, logging, and automatic backups for the vector database and relational database.  Implement rate limiting and input validation to protect against abuse.

## 7. Documentation and Testing

Expand documentation to include developer setup, API usage, and contribution guidelines.  Write unit tests and integration tests for all components, including ingestion, retrieval, and LLM response.  Ensure CI/CD pipelines run tests and maintain code quality.
