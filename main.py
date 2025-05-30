import os
import discord
import asyncio
import json
import psycopg2
from datetime import datetime
from discord.ext import commands
from anthropic import Anthropic
from itertools import cycle
from dotenv import load_dotenv

load_dotenv()

# 설정 및 환경변수
DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
ANTHROPIC_API_KEYS = [
    os.environ['ANTHROPIC_API_KEY_1'],
    os.environ['ANTHROPIC_API_KEY_2']
]

# API 키가 제대로 설정되었는지 확인
if not DISCORD_TOKEN or not any(ANTHROPIC_API_KEYS):
    raise ValueError("필요한 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 시스템 프롬프트 로드
SYSTEM_PROMPT = ""

class DatabaseManager:
    def __init__(self):
        self.conn = psycopg2.connect(os.environ['DATABASE_URL'])
        self.setup_database()
        self.backup_interval = 300  # 5분마다 백업
        
    def setup_database(self):
        """데이터베이스 테이블 초기 설정"""
        with self.conn.cursor() as cur:
            # 채팅 백업용 테이블
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    channel_id BIGINT NOT NULL,
                    message_history JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- 채널별 설정 저장용 테이블
                CREATE TABLE IF NOT EXISTS channel_settings (
                    channel_id BIGINT PRIMARY KEY,
                    is_active BOOLEAN DEFAULT true,
                    last_backup TIMESTAMP,
                    system_prompt TEXT,
                    permanent_history JSONB,
                    temperature FLOAT DEFAULT 0.7,
                    max_tokens INT DEFAULT 4000
                );
                
                CREATE TABLE IF NOT EXISTS manual_history (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_by BIGINT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_current BOOLEAN DEFAULT true
                );
            """)
        self.conn.commit()
        print("데이터베이스 설정 완료")

    async def update_manual(self, content: str, user_id: int):
        """새로운 매뉴얼 내용 저장"""
        try:
            with self.conn.cursor() as cur:
                # 기존 현재 버전 비활성화
                cur.execute(
                    "UPDATE manual_history SET is_current = false WHERE is_current = true"
                )
                
                # 새 버전 추가
                cur.execute(
                    """
                    INSERT INTO manual_history (content, updated_by)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (content, user_id)
                )
                new_id = cur.fetchone()[0]
            self.conn.commit()
            return new_id
        except Exception as e:
            print(f"매뉴얼 업데이트 중 오류: {e}")
            self.conn.rollback()
            raise
    
    def get_current_manual(self):
        """현재 활성화된 매뉴얼 내용 조회"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM manual_history WHERE is_current = true"
            )
            result = cur.fetchone()
            return result[0] if result else None
    
    def get_manual_history(self, limit=5):
        """매뉴얼 변경 이력 조회"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, updated_by, updated_at, is_current
                FROM manual_history
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            return cur.fetchall()
    
    async def start_backup_loop(self):
        """주기적 백업 실행"""
        while True:
            await self.backup_all_channels()
            await asyncio.sleep(self.backup_interval)
    
    async def backup_all_channels(self):
        """모든 채널의 대화 내용 백업"""
        try:
            with self.conn.cursor() as cur:
                for channel_id, messages in channel_message_history.items():
                    if messages:  # 메시지가 있는 경우만 백업
                        cur.execute(
                            """
                            INSERT INTO chat_history (channel_id, message_history)
                            VALUES (%s, %s)
                            """,
                            (channel_id, json.dumps(messages))
                        )
                        
                        # 마지막 백업 시간 업데이트
                        cur.execute(
                            """
                            INSERT INTO channel_settings (channel_id, last_backup)
                            VALUES (%s, CURRENT_TIMESTAMP)
                            ON CONFLICT (channel_id) 
                            DO UPDATE SET last_backup = CURRENT_TIMESTAMP
                            """,
                            (channel_id,)
                        )
            self.conn.commit()
            print(f"모든 채널 백업 완료: {datetime.now()}")
            
        except Exception as e:
            print(f"백업 중 오류 발생: {e}")
            self.conn.rollback()
    
    async def load_channel_history(self, channel_id):
        """채널의 가장 최근 백업 불러오기"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT message_history 
                    FROM chat_history 
                    WHERE channel_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                    """,
                    (channel_id,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]
        except Exception as e:
            print(f"히스토리 불러오기 실패: {e}")
        return []
    
    def save_channel_context(self, channel_id, system_prompt=None, permanent_history=None, temperature=None, max_tokens=None):
        """채널별 컨텍스트 정보 저장"""
        try:
            # 디버깅을 위한 파라미터 출력
            print(f"저장 시도 - 채널: {channel_id}, 프롬프트: {system_prompt is not None}, 고정대화: {permanent_history is not None}, 온도: {temperature}, 토큰: {max_tokens}")

            update_fields = []
            params = [channel_id]
            
            if system_prompt is not None:
                update_fields.append("system_prompt = %s")
                params.append(system_prompt)
                
            if permanent_history is not None:
                update_fields.append("permanent_history = %s")
                params.append(json.dumps(permanent_history))
                
            if temperature is not None:
                update_fields.append("temperature = %s")
                params.append(temperature)
                
            if max_tokens is not None:
                update_fields.append("max_tokens = %s")
                params.append(max_tokens)
                
            if not update_fields:
                return False
                
            with self.conn.cursor() as cur:
                query = f"""
                    INSERT INTO channel_settings (channel_id, {', '.join(field.split(' = ')[0] for field in update_fields)})
                    VALUES (%s, {', '.join(['%s'] * len(update_fields))})
                    ON CONFLICT (channel_id) 
                    DO UPDATE SET {', '.join(update_fields)}
                """
                cur.execute(query, params)
            self.conn.commit()
            print(f"채널 {channel_id}의 컨텍스트 정보 저장 완료")
            return True
        except Exception as e:
            print(f"컨텍스트 저장 중 오류: {e}")
            import traceback
            traceback.print_exc()  # 더 상세한 에러 스택 출력
            self.conn.rollback()
            return False
            
    def load_channel_context(self, channel_id):
        """채널별 컨텍스트 정보 로드"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT system_prompt, permanent_history, temperature, max_tokens
                    FROM channel_settings
                    WHERE channel_id = %s
                    """,
                    (channel_id,)
                )
                result = cur.fetchone()
                if result:
                    system_prompt, permanent_history, temperature, max_tokens = result
                    return system_prompt, permanent_history, temperature, max_tokens
            return None, None, 0.7, 4000  # 기본 temperature 값 0.7 반환, 기본 max_tokens 값 4000 반환
        except Exception as e:
            print(f"컨텍스트 로드 중 오류: {e}")
            return None, None, 0.7, 4000  # 오류 발생 시 기본값 반환
    
    def cleanup_old_backups(self, days=30):
        """오래된 백업 삭제"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM chat_history 
                    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
                    """,
                    (days,)
                )
            self.conn.commit()
        except Exception as e:
            print(f"오래된 백업 정리 중 오류: {e}")
            self.conn.rollback()

class AnthropicClient:
    def __init__(self, api_keys):
        self.clients = [Anthropic(api_key=key) for key in api_keys]
        self.client_cycle = cycle(self.clients)
        self.current_client_index = 0
    
    def get_next_client(self):
        client = next(self.client_cycle)
        return client
    
    
    def get_specific_client(self, index):
        return self.clients[index % len(self.clients)]

def trim_history_by_count(messages, max_messages=30):
    """메시지 개수 제한"""
    if max_messages <= 0:
        print(f"메시지 개수 초과: {len(messages)} -> 0로 제한")
        return []
    
    if len(messages) > max_messages:
        print(f"메시지 개수 초과: {len(messages)} -> {max_messages}로 제한")
        return messages[-max_messages:]
    
    return messages

async def try_api_call(channel_id, max_retries=3):
    """API 호출 재시도 로직"""
    used_clients = set()
    
    # 채널별 컨텍스트 정보 로드
    channel_system_prompt = channel_system_prompts.get(channel_id, SYSTEM_PROMPT)
    permanent = channel_permanent_history.get(channel_id, [])
    recent = channel_message_history.get(channel_id, [])
    temperature = channel_temperature.get(channel_id, 0.7)  # 기본값 0.7
    max_tokens = channel_max_tokens.get(channel_id, 4000)  # 기본값 4000
    
    # 메시지가 없으면 API 호출이 실패하므로, 최소 1개의 메시지가 필요
    if not recent and not permanent:
        print("메시지가 없어 API 호출을 진행할 수 없습니다.")
        return None

    # 완전한 메시지 히스토리 구성 (최대 20개 메시지까지만 - 유저 10개, 클로드 10개)
    full_history = permanent + recent
    
    # 컨텍스트 정보 로깅
    print(f"\n채널 {channel_id} API 호출 컨텍스트 정보:")
    print(f"- 시스템 프롬프트: {len(channel_system_prompt)} 자")
    print(f"- 고정 대화: {len(permanent)}개 메시지")
    print(f"- 최근 대화: {len(recent)}개 메시지")
    print(f"- 총 메시지: {len(full_history)}개")
    print(f"- 온도(Temperature): {temperature}")
    print(f"- 최대 토큰(Max Tokens): {max_tokens}")
    
    for attempt in range(max_retries):
        client = anthropic.get_next_client()
        
        while client in used_clients and len(used_clients) < len(anthropic.clients):
            client = anthropic.get_next_client()
            
        used_clients.add(client)
        
        try:
            response = client.messages.create(
                model="claude-3-7-sonnet-20250219",  # 3.7 Sonnet 모델 사용
                max_tokens=max_tokens,  # 채널별 max_tokens 값 사용
                temperature=temperature,  # 채널별 temperature 값 사용
                system=channel_system_prompt,
                messages=full_history
            )
            print(f"API 호출 성공 (시도: {attempt + 1}, temperature: {temperature}, max_tokens: {max_tokens})")
            return response
            
        except Exception as e:
            print(f"API 호출 시도 {attempt + 1} 실패: {e}")
            if attempt == max_retries - 1:
                raise e
            await asyncio.sleep(1)
    
    return None

# Discord 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Anthropic 클라이언트 초기화
anthropic = AnthropicClient(ANTHROPIC_API_KEYS)

# 채널별 메시지 히스토리 관리
channel_message_history = {}  # 최근 대화 내용 (가변)
channel_permanent_history = {}  # 고정 대화 내용
channel_system_prompts = {}  # 채널별 시스템 프롬프트
channel_temperature = {}  # 채널별 temperature 값
channel_max_tokens = {}  # 채널별 max_tokens 값

# 채널별 활성화 상태 관리
channel_active_status = {}

# 명령어 응답 추적을 위한 변수
command_response_ids = set()  # 명령어 응답 메시지 ID를 저장

# 데이터베이스 매니저 초기화
db = DatabaseManager()

@bot.event
async def on_ready():
    global SYSTEM_PROMPT
    
    print(f'{bot.user.name}이 성공적으로 시작되었습니다!')
    
    # 채널 설정 불러오기
    with db.conn.cursor() as cur:
        cur.execute("SELECT channel_id, is_active, system_prompt, permanent_history, temperature, max_tokens FROM channel_settings")
        for row in cur.fetchall():
            if len(row) >= 2:
                channel_id, is_active = row[0], row[1]
                channel_active_status[channel_id] = is_active
                
                if len(row) >= 6:
                    system_prompt, permanent_history, temperature, max_tokens = row[2], row[3], row[4], row[5]
                    if system_prompt:
                        channel_system_prompts[channel_id] = system_prompt
                    if permanent_history:
                        channel_permanent_history[channel_id] = permanent_history
                    if temperature is not None:
                        channel_temperature[channel_id] = temperature
                    if max_tokens is not None:
                        channel_max_tokens[channel_id] = max_tokens
    
    # DB에서 현재 매뉴얼 로드
    manual_content = db.get_current_manual()
    if manual_content:
        SYSTEM_PROMPT = manual_content
    else:
        print("⚠️ 등록된 매뉴얼이 없습니다. '!manual update' 명령어로 매뉴얼을 등록해주세요.")

    # 백업 루프 시작
    print("백업 루프 시작 시도 중...")
    bot.loop.create_task(db.start_backup_loop())
    print("백업 루프 시작 완료")

@bot.command(name='setup')
@commands.has_role('Manual Manager')
async def setup_context(ctx, action=None):
    """컨텍스트 설정 명령어"""
    channel_id = ctx.channel.id
    
    if not action:
        message = await ctx.send("❓ 사용 가능한 명령어:\n!setup prompt (txt 파일 첨부)\n!setup initial (json 파일 첨부)\n!setup status\n!setup clear")
        command_response_ids.add(message.id)  # 명령어 응답 ID 추적
        return
        
    if action == 'prompt':
        if len(ctx.message.attachments) == 0:
            message = await ctx.send("❌ 시스템 프롬프트가 들어있는 txt 파일을 첨부해주세요!")
            command_response_ids.add(message.id)
            return
            
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith('.txt'):
            message = await ctx.send("❌ txt 파일만 업로드 가능합니다!")
            command_response_ids.add(message.id)
            return
            
        try:
            content = await attachment.read()
            prompt_text = content.decode('utf-8')
            
            # 기본적인 유효성 검사
            if len(prompt_text.strip()) < 10:
                message = await ctx.send("❌ 프롬프트 내용이 너무 짧습니다!")
                command_response_ids.add(message.id)
                return
                
            # 채널별 시스템 프롬프트 설정
            channel_system_prompts[channel_id] = prompt_text
            
            # DB에 저장
            db.save_channel_context(channel_id, system_prompt=prompt_text)
            
            message = await ctx.send(f"✅ 채널별 시스템 프롬프트가 설정되었습니다! ({len(prompt_text)} 자)")
            command_response_ids.add(message.id)
            print(f"채널 {channel_id}의 시스템 프롬프트 설정 완료 ({len(prompt_text)} 자)")
            
        except Exception as e:
            message = await ctx.send(f"❌ 프롬프트 설정 중 오류가 발생했습니다: {str(e)}")
            command_response_ids.add(message.id)
            
    elif action == 'initial':
        if len(ctx.message.attachments) == 0:
            message = await ctx.send("❌ 초기 대화 내용이 들어있는 json 파일을 첨부해주세요!")
            command_response_ids.add(message.id)
            return
            
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith('.json'):
            message = await ctx.send("❌ json 파일만 업로드 가능합니다!")
            command_response_ids.add(message.id)
            return
            
        try:
            content = await attachment.read()
            json_text = content.decode('utf-8')
            initial_messages = json.loads(json_text)
            
            # 기본적인 유효성 검사
            if not isinstance(initial_messages, list) or len(initial_messages) == 0:
                message = await ctx.send("❌ 유효한 메시지 형식이 아닙니다. JSON 배열 형태여야 합니다.")
                command_response_ids.add(message.id)
                return
                
            # 메시지 형식 검증
            for msg in initial_messages:
                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                    message = await ctx.send("❌ 메시지 형식이 올바르지 않습니다. 각 메시지는 'role'과 'content' 필드를 포함해야 합니다.")
                    command_response_ids.add(message.id)
                    return
                if msg["role"] not in ["user", "assistant"]:
                    message = await ctx.send("❌ 메시지 역할이 올바르지 않습니다. 'user' 또는 'assistant'만 가능합니다.")
                    command_response_ids.add(message.id)
                    return
                
            # 채널별 고정 대화 내용 설정
            channel_permanent_history[channel_id] = initial_messages
            
            # DB에 저장
            db.save_channel_context(channel_id, permanent_history=initial_messages)
            
            message = await ctx.send(f"✅ 초기 대화 컨텍스트가 설정되었습니다! ({len(initial_messages)}개 메시지)")
            command_response_ids.add(message.id)
            print(f"채널 {channel_id}의 초기 대화 컨텍스트 설정 완료 ({len(initial_messages)}개 메시지)")
            
        except json.JSONDecodeError:
            message = await ctx.send("❌ 유효한 JSON 형식이 아닙니다.")
            command_response_ids.add(message.id)
        except Exception as e:
            message = await ctx.send(f"❌ 초기 대화 설정 중 오류가 발생했습니다: {str(e)}")
            command_response_ids.add(message.id)
            
    elif action == 'status':
        # 현재 컨텍스트 상태 확인
        system_prompt = channel_system_prompts.get(channel_id, SYSTEM_PROMPT)
        permanent = channel_permanent_history.get(channel_id, [])
        recent = channel_message_history.get(channel_id, [])
        temperature = channel_temperature.get(channel_id, 0.7)
        max_tokens = channel_max_tokens.get(channel_id, 4000)
        
        status_text = f"📊 채널 {ctx.channel.name}의 컨텍스트 상태:\n"
        status_text += f"- 시스템 프롬프트: {'설정됨' if system_prompt else '기본값 사용'} ({len(system_prompt) if system_prompt else 0} 자)\n"
        status_text += f"- 고정 대화: {len(permanent)}개 메시지\n"
        status_text += f"- 최근 대화: {len(recent)}개 메시지\n"
        status_text += f"- 온도(Temperature): {temperature}\n"
        status_text += f"- 최대 토큰(Max Tokens): {max_tokens}"
        
        message = await ctx.send(status_text)
        command_response_ids.add(message.id)
        
    elif action == 'clear':
        # 컨텍스트 초기화 (최근 대화만)
        if channel_id in channel_message_history:
            old_count = len(channel_message_history[channel_id])
            channel_message_history[channel_id] = []
            message = await ctx.send(f"✅ 최근 대화 내용이 초기화되었습니다. ({old_count}개 메시지 삭제)")
            command_response_ids.add(message.id)
            print(f"채널 {channel_id}의 최근 대화 내용 초기화")
        else:
            message = await ctx.send("ℹ️ 초기화할 대화 내용이 없습니다.")
            command_response_ids.add(message.id)
            
    else:
        message = await ctx.send("❌ 잘못된 명령어입니다. `!setup`을 입력하여 사용 가능한 명령어를 확인하세요.")
        command_response_ids.add(message.id)

@bot.command(name='temp')
@commands.has_role('Manual Manager')
async def set_temperature(ctx, value=None):
    """Temperature 설정 명령어"""
    channel_id = ctx.channel.id
    
    if value is None:
        current_temp = channel_temperature.get(channel_id, 0.7)
        message = await ctx.send(f"🌡️ 현재 이 채널의 온도(Temperature) 설정값: {current_temp}\n"
                               f"설정 방법: `!temp [값]` (범위: 0.0~1.0, 예: !temp 0.7)")
        command_response_ids.add(message.id)
        return
    
    try:
        temp_value = float(value)
        if temp_value < 0.0 or temp_value > 1.0:
            message = await ctx.send("❌ 온도값은 0.0에서 1.0 사이여야 합니다.")
            command_response_ids.add(message.id)
            return
        
        # 채널별 temperature 설정
        channel_temperature[channel_id] = temp_value
        
        # DB에 저장
        db.save_channel_context(channel_id, temperature=temp_value)
        
        message = await ctx.send(f"✅ 온도(Temperature)가 {temp_value}로 설정되었습니다.")
        command_response_ids.add(message.id)
        print(f"채널 {channel_id}의 온도 설정 완료: {temp_value}")
        
    except ValueError:
        message = await ctx.send("❌ 유효한 숫자 형식이 아닙니다. 예: !temp 0.7")
        command_response_ids.add(message.id)
    except Exception as e:
        message = await ctx.send(f"❌ 온도 설정 중 오류가 발생했습니다: {str(e)}")
        command_response_ids.add(message.id)

@bot.command(name='tokens')
@commands.has_role('Manual Manager')
async def set_max_tokens(ctx, value=None):
    """최대 토큰 설정 명령어"""
    channel_id = ctx.channel.id
    
    if value is None:
        current_tokens = channel_max_tokens.get(channel_id, 4000)
        message = await ctx.send(f"🔢 현재 이 채널의 최대 토큰(Max Tokens) 설정값: {current_tokens}\n"
                               f"설정 방법: `!tokens [값]` (범위: 1~4096, 예: !tokens 4000)")
        command_response_ids.add(message.id)
        return
    
    try:
        tokens_value = int(value)
        if tokens_value < 1 or tokens_value > 4096:
            message = await ctx.send("❌ 최대 토큰값은 1에서 4096 사이여야 합니다.")
            command_response_ids.add(message.id)
            return
        
        # 채널별 max_tokens 설정
        channel_max_tokens[channel_id] = tokens_value
        
        # DB에 저장
        db.save_channel_context(channel_id, max_tokens=tokens_value)
        
        message = await ctx.send(f"✅ 최대 토큰(Max Tokens)이 {tokens_value}로 설정되었습니다.")
        command_response_ids.add(message.id)
        print(f"채널 {channel_id}의 최대 토큰 설정 완료: {tokens_value}")
        
    except ValueError:
        message = await ctx.send("❌ 유효한 숫자 형식이 아닙니다. 예: !tokens 4000")
        command_response_ids.add(message.id)
    except Exception as e:
        message = await ctx.send(f"❌ 최대 토큰 설정 중 오류가 발생했습니다: {str(e)}")
        command_response_ids.add(message.id)


@bot.command(name='manual')
@commands.has_role('Manual Manager')
async def manual(ctx, action=None):
    """매뉴얼 관리 명령어"""
    if not action:
        message = await ctx.send("❓ 사용 가능한 명령어:\n!manual update (txt 파일 첨부)\n!manual show\n!manual history")
        command_response_ids.add(message.id)
        return

    if action == 'update':
        if len(ctx.message.attachments) == 0:
            message = await ctx.send("❌ txt 파일을 첨부해주세요!")
            command_response_ids.add(message.id)
            return
            
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith('.txt'):
            message = await ctx.send("❌ txt 파일만 업로드 가능합니다!")
            command_response_ids.add(message.id)
            return
            
        try:
            content = await attachment.read()
            manual_text = content.decode('utf-8')
            
            # 기본적인 유효성 검사
            if len(manual_text.strip()) < 10:
                message = await ctx.send("❌ 매뉴얼 내용이 너무 짧습니다!")
                command_response_ids.add(message.id)
                return
                
            # 매뉴얼 업데이트
            new_id = await db.update_manual(manual_text, ctx.author.id)
            
            # 전역 변수 업데이트
            global SYSTEM_PROMPT
            SYSTEM_PROMPT = manual_text
            
            message = await ctx.send(f"✅ 매뉴얼이 성공적으로 업데이트되었습니다! (버전 ID: {new_id})")
            command_response_ids.add(message.id)
            
        except Exception as e:
            message = await ctx.send(f"❌ 업데이트 중 오류가 발생했습니다: {str(e)}")
            command_response_ids.add(message.id)
            
    elif action == 'show':
        manual_content = db.get_current_manual()
        if not manual_content:
            message = await ctx.send("❌ 저장된 매뉴얼이 없습니다.")
            command_response_ids.add(message.id)
            return
            
        # 긴 내용은 파일로 전송
        if len(manual_content) > 1900:
            with open('current_manual.txt', 'w', encoding='utf-8') as f:
                f.write(manual_content)
            message = await ctx.send("📄 현재 매뉴얼 내용:", file=discord.File('current_manual.txt'))
            command_response_ids.add(message.id)
            os.remove('current_manual.txt')
        else:
            message = await ctx.send(f"📄 현재 매뉴얼 내용:\n```\n{manual_content}\n```")
            command_response_ids.add(message.id)
            
    elif action == 'history':
        history = db.get_manual_history()
        if not history:
            message = await ctx.send("📜 매뉴얼 변경 이력이 없습니다.")
            command_response_ids.add(message.id)
            return
            
        history_text = "📜 최근 매뉴얼 변경 이력:\n"
        for id, updated_by, updated_at, is_current in history:
            user = bot.get_user(updated_by)
            username = user.name if user else f"Unknown ({updated_by})"
            current_mark = "✅ " if is_current else "  "
            history_text += f"{current_mark}ID {id}: {username} - {updated_at}\n"
            
        message = await ctx.send(history_text)
        command_response_ids.add(message.id)
        
    else:
        message = await ctx.send("❌ 잘못된 명령어입니다. `!manual`을 입력하여 사용 가능한 명령어를 확인하세요.")
        command_response_ids.add(message.id)

@bot.command(name='status')
async def check_status(ctx):
    """클로드 봇 상태 확인 명령어"""
    channel_id = ctx.channel.id
    status = "활성화" if channel_active_status.get(channel_id, True) else "비활성화"
    
    # 추가 컨텍스트 정보
    system_prompt = channel_system_prompts.get(channel_id, SYSTEM_PROMPT)
    permanent = channel_permanent_history.get(channel_id, [])
    recent = channel_message_history.get(channel_id, [])
    temperature = channel_temperature.get(channel_id, 0.7)
    max_tokens = channel_max_tokens.get(channel_id, 4000)
    
    status_text = f"🤖 현재 이 채널에서 Claude는 {status} 상태입니다.\n"
    status_text += f"- 시스템 프롬프트: {'설정됨' if system_prompt else '기본값 사용'} ({len(system_prompt) if system_prompt else 0} 자)\n"
    status_text += f"- 고정 대화: {len(permanent)}개 메시지\n"
    status_text += f"- 최근 대화: {len(recent)}개 메시지\n"
    status_text += f"- 온도(Temperature): {temperature}\n"
    status_text += f"- 최대 토큰(Max Tokens): {max_tokens}"
    
    message = await ctx.send(status_text)
    command_response_ids.add(message.id)

@bot.event
async def on_message(message):
    # 봇 명령어 처리
    await bot.process_commands(message)
    
    # 봇 메시지 무시
    if message.author == bot.user:
        return
    
    # 명령어 메시지 무시 (명령어로 시작하는 메시지는 Claude 응답 처리하지 않음)
    if message.content.startswith('!'):
        return
        
    channel_id = message.channel.id
    
    # 해당 채널이 비활성화 상태면 응답하지 않음
    if not channel_active_status.get(channel_id, True):
        return
    
    # 채널별 메시지 히스토리 초기화 (없으면)
    if channel_id not in channel_message_history:
        channel_message_history[channel_id] = []
    
    # 메시지 내용 구성 (텍스트 + 첨부파일 정보)
    content = message.content
    
    # 첨부파일 처리
    if message.attachments:
        for attachment in message.attachments:
            file_ext = os.path.splitext(attachment.filename)[1].lower()
            
            if file_ext in ['.txt', '.md', '.csv', '.py', '.js', '.html', '.css']:
                try:
                    file_content = await attachment.read()
                    file_text = file_content.decode('utf-8')
                    content += f"\n\n첨부파일 ({attachment.filename})의 내용:\n{file_text}"
                except Exception as e:
                    print(f"파일 읽기 오류: {e}")
                    content += f"\n\n첨부파일 ({attachment.filename})을 읽을 수 없습니다."
            else:
                content += f"\n\n첨부파일: {attachment.filename} (크기: {attachment.size} bytes)"
    
    # 새 메시지 추가
    new_message = {
        "role": "user",
        "content": content
    }
    
    # 메시지 히스토리에 새 메시지 추가
    channel_message_history[channel_id].append(new_message)
    
    # 최대 20개 메시지만 유지 (유저 10개, 클로드 10개 최대)
    MAX_MESSAGES = 20
    if len(channel_message_history[channel_id]) > MAX_MESSAGES:
        channel_message_history[channel_id] = channel_message_history[channel_id][-MAX_MESSAGES:]
    
    # API 호출 및 응답 처리
    async with message.channel.typing():
        try:
            response = await try_api_call(channel_id)
            
            if response:
                response_text = response.content[0].text
                
                # 디버깅: API 응답의 원시 형태 확인
                #print(f"\n---- API 응답 원본 (채널: {channel_id}) ----")
                #print(f"응답 길이: {len(response_text)} 글자")
                #newline_count = response_text.count('\n')  # 변수에 저장
                #print(f"줄바꿈 문자 수: {newline_count}")
                #print(f"첫 200자: {repr(response_text[:200])}")
                #print("-----------------------------------\n")
                
                # 응답에 파일이 포함된 경우 파일로 저장하여 전송
                if "```" in response_text:
                    code_blocks = []
                    current_block = ""
                    is_in_block = False
                    
                    for line in response_text.split('\n'):
                        if line.startswith('```'):
                            if is_in_block:
                                code_blocks.append(current_block)
                                current_block = ""
                            is_in_block = not is_in_block
                        elif is_in_block:
                            current_block += line + '\n'
                    
                    # 코드 블록이 있으면 파일로 저장하여 전송
                    for i, code in enumerate(code_blocks):
                        if code.strip():
                            file_name = f'code_{i+1}.txt'
                            with open(file_name, 'w', encoding='utf-8') as f:
                                f.write(code)
                            await message.channel.send(file=discord.File(file_name))
                            os.remove(file_name)
                
                # 일반 텍스트 응답 전송
                if len(response_text) > 2000:
                    for i in range(0, len(response_text), 2000):
                        chunk = response_text[i:i+2000]
                        # 디버깅: 각 청크의 첫 부분과 마지막 부분을 확인
                        print(f"청크 {i//2000 + 1} 첫 20자: {repr(chunk[:20])}")
                        print(f"청크 {i//2000 + 1} 마지막 20자: {repr(chunk[-20:] if len(chunk) >= 20 else chunk)}")
                        await message.channel.send(chunk)
                else:
                    await message.channel.send(response_text)
                
                # 클로드의 응답을 메시지 히스토리에 추가
                claude_response = {
                    "role": "assistant",
                    "content": response_text
                }
                channel_message_history[channel_id].append(claude_response)
                
                # 최대 20개 메시지만 유지 (유저 10개, 클로드 10개 최대)
                if len(channel_message_history[channel_id]) > MAX_MESSAGES:
                    channel_message_history[channel_id] = channel_message_history[channel_id][-MAX_MESSAGES:]
                
            else:
                await message.channel.send("죄송합니다. API 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요.")
                    
        except Exception as e:
            print(f"최종 에러: {e}")
            await message.channel.send("죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

# 봇 실행
bot.run(DISCORD_TOKEN)   