# Controle de Aulas — API Flask

API REST do TCC **Controle de Aulas**, preparada para aplicativo Android em
Kotlin/Jetpack Compose, banco PostgreSQL no Neon e publicação na Vercel.

## Regras implementadas

- O primeiro cadastro cria o único usuário inicial com papel `ADMIN`.
- Depois do cadastro inicial, somente o administrador cria e gerencia professores.
- Administradores criam e alteram salas, incluindo nome e quantidade de aulas.
- Professores visualizam salas e agendam aulas disponíveis.
- Uma sala não pode ter dois agendamentos no mesmo dia e número de aula.
- O administrador não agenda aulas, mas pode remover qualquer agendamento.
- O professor pode remover apenas um agendamento feito por ele mesmo.
- Senhas são armazenadas como hashes, nunca como texto puro.

## Estrutura

```text
controle-aulas-api/
├── api/index.py          # Entrada usada pela Vercel
├── app/
│   ├── __init__.py       # Configuração e fábrica da aplicação
│   ├── auth.py           # Cadastro inicial, login e autorização
│   ├── extensions.py     # Banco, JWT, CORS e migrações
│   ├── models.py         # User, Room e Schedule
│   └── routes.py         # Professores, salas e agendamentos
├── tests/test_api.py
├── .env.example
├── requirements.txt
├── run.py
└── vercel.json
```

## Executar localmente

Requer Python 3.11 ou mais recente.

```bash
python -m venv .venv
```

Ative o ambiente virtual no Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Instale as dependências e configure o ambiente:

```bash
pip install -r requirements.txt
copy .env.example .env
```

Para um teste rápido sem Neon, remova `DATABASE_URL` do `.env`; a API usará
SQLite local. Crie as tabelas e execute:

```bash
flask --app run.py db init
flask --app run.py db migrate -m "estrutura inicial"
flask --app run.py db upgrade
flask --app run.py run --debug
```

Acesse `http://127.0.0.1:5000/api/health`.

## Configurar o Neon

1. Crie um projeto no Neon.
2. Copie a connection string com conexão agrupada (hostname contendo `-pooler`).
3. No `.env`, informe-a como `DATABASE_URL`.
4. Mantenha `sslmode=require` no final da URL.
5. Gere uma chave longa e aleatória para `JWT_SECRET_KEY`.
6. Execute `flask --app run.py db upgrade` antes da primeira utilização.

Nunca envie o arquivo `.env` ao GitHub.

## Rotas principais

| Método | Rota | Permissão | Finalidade |
|---|---|---|---|
| POST | `/api/auth/bootstrap` | Pública, uma única vez | Criar ADMIN inicial |
| POST | `/api/auth/login` | Pública | Entrar e receber JWT |
| GET | `/api/me` | Autenticado | Obter usuário atual |
| GET/POST | `/api/teachers` | ADMIN | Listar/criar professores |
| PATCH | `/api/teachers/{id}` | ADMIN | Gerenciar professor |
| GET | `/api/rooms` | Autenticado | Listar salas |
| POST | `/api/rooms` | ADMIN | Criar sala |
| PATCH | `/api/rooms/{id}` | ADMIN | Alterar sala |
| GET | `/api/rooms/{id}/schedules` | Autenticado | Consultar agenda por período |
| POST | `/api/rooms/{id}/schedules` | PROFESSOR | Agendar uma aula |
| DELETE | `/api/schedules/{id}` | ADMIN ou autor | Remover agendamento |

Na consulta da agenda, use por exemplo:
`?start=2026-09-09&end=2026-09-15`.

## Exemplos JSON

Cadastro inicial e login:

```json
{ "name": "Administrador", "password": "uma-senha-segura" }
```

Criar sala:

```json
{ "name": "Sala 1", "lessonCount": 6 }
```

Agendar aula:

```json
{ "date": "2026-09-10", "lessonNumber": 2 }
```

No Android, envie o token nas rotas protegidas:

```http
Authorization: Bearer SEU_TOKEN
```

## Publicar na Vercel

1. Envie este diretório para um repositório GitHub.
2. Importe o repositório na Vercel.
3. Cadastre `DATABASE_URL`, `JWT_SECRET_KEY` e `FRONTEND_ORIGINS` nas variáveis.
4. Faça o deploy.
5. Teste `https://seu-projeto.vercel.app/api/health`.

O Android deverá usar a URL HTTPS publicada como URL base do Retrofit.

## Testes

Instale pytest e execute:

```bash
pip install pytest
pytest -q
```

O teste incluído cobre criação do ADMIN, bloqueio de um segundo cadastro inicial,
criação de professor e sala, agendamento pelo professor, bloqueio do agendamento
pelo ADMIN e remoção administrativa.

