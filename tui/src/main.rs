use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    ExecutableCommand,
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Paragraph, Wrap},
    Terminal,
};
use serde::{Deserialize, Serialize};
use std::io;

#[derive(Serialize)]
struct TaskRequest {
    task: String,
}

#[derive(Deserialize)]
struct TaskResponse {
    task_id: Option<usize>,
    error: Option<String>,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum ServerMessage {
    Log { log: String },
    Done { done: String },
}

#[derive(Clone, PartialEq)]
enum Status {
    Idle,
    Running,
    Done(String),
    Error(String),
}

#[tokio::main]
async fn main() -> io::Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    stdout.execute(EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result = run(&mut terminal).await;

    disable_raw_mode()?;
    terminal.backend_mut().execute(LeaveAlternateScreen)?;
    result
}

async fn run(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>) -> io::Result<()> {
    let mut input = String::new();
    let mut logs: Vec<String> = vec![
        "Browser Agent - type a task and press Enter".into(),
        "Ctrl+C to quit".into(),
    ];
    let mut status = Status::Idle;
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<ServerMessage>();

    loop {
        while let Ok(msg) = rx.try_recv() {
            match msg {
                ServerMessage::Log { log } => logs.push(log),
                ServerMessage::Done { done } => {
                    logs.push(format!("Done: {}", done));
                    status = Status::Done(done);
                }
            }
        }

        terminal.draw(|f| {
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(3),
                    Constraint::Min(6),
                    Constraint::Length(1),
                ])
                .split(f.size());

            let input_style = match &status {
                Status::Running => Style::default().fg(Color::Yellow),
                _ => Style::default().fg(Color::Cyan),
            };
            let input_widget = Paragraph::new(input.as_str())
                .style(input_style)
                .block(Block::default().borders(Borders::ALL).title(" Task "))
                .wrap(Wrap { trim: false });
            f.render_widget(input_widget, chunks[0]);

            let log_height = chunks[1].height.saturating_sub(2) as usize;
            let visible: Vec<ListItem> = logs
                .iter()
                .rev()
                .take(log_height)
                .rev()
                .map(|l| ListItem::new(Line::from(Span::raw(l.clone()))))
                .collect();
            let log_widget = List::new(visible)
                .block(Block::default().borders(Borders::ALL).title(" Agent Log "));
            f.render_widget(log_widget, chunks[1]);

            let (status_text, status_color) = match &status {
                Status::Idle => ("  IDLE - type a task and press Enter", Color::DarkGray),
                Status::Running => ("  RUNNING - watch the browser...", Color::Yellow),
                Status::Done(_) => ("  DONE - press Enter to run another task", Color::Green),
                Status::Error(e) => (e.as_str(), Color::Red),
            };
            let status_bar = Paragraph::new(status_text)
                .style(Style::default().fg(status_color).add_modifier(Modifier::BOLD));
            f.render_widget(status_bar, chunks[2]);
        })?;

        if event::poll(std::time::Duration::from_millis(50))? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                        break;
                    }
                    KeyCode::Enter if !input.is_empty() && status != Status::Running => {
                        let task = input.trim().to_string();
                        input.clear();
                        logs.push(format!(">>> {}", task));
                        status = Status::Running;

                        let tx2 = tx.clone();
                        tokio::spawn(async move {
                            if let Err(e) = send_task(task, tx2.clone()).await {
                                let _ = tx2.send(ServerMessage::Log { 
                                    log: format!("Error: {}", e) 
                                });
                            }
                        });
                    }
                    KeyCode::Backspace => {
                        input.pop();
                    }
                    KeyCode::Char(c) if status != Status::Running => {
                        input.push(c);
                    }
                    _ => {}
                }
            }
        }
    }

    Ok(())
}

async fn send_task(task: String, tx: tokio::sync::mpsc::UnboundedSender<ServerMessage>) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let client = reqwest::Client::new();
    
    let response = client
        .post("http://127.0.0.1:9000/task")
        .json(&TaskRequest { task })
        .send()
        .await?;
    
    let task_resp: TaskResponse = response.json().await?;
    
    if let Some(error) = task_resp.error {
        let _ = tx.send(ServerMessage::Log { log: format!("Error: {}", error) });
        return Ok(());
    }
    
    let task_id = task_resp.task_id.ok_or("No task_id returned")?;
    
    let stream_url = format!("http://127.0.0.1:9000/task/{}/stream", task_id);
    
    let response = client
        .get(&stream_url)
        .send()
        .await?;
    
    let mut stream = response.bytes_stream();
    
    let mut buffer = String::new();
    
    use futures_util::StreamExt;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if let Ok(text) = String::from_utf8(chunk.to_vec()) {
            buffer.push_str(&text);
            
            while let Some(pos) = buffer.find('\n') {
                let line = buffer[..pos].to_string();
                buffer = buffer[pos + 1..].to_string();
                
                if let Some(stripped) = line.strip_prefix("data: ") {
                    if let Ok(msg) = serde_json::from_str::<ServerMessage>(stripped) {
                        let _ = tx.send(msg);
                    }
                }
            }
        }
    }
    
    Ok(())
}
