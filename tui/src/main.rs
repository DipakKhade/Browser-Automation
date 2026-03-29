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
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::TcpStream,
    sync::mpsc,
};

#[derive(Serialize)]
struct Request {
    task: String,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum ServerMessage {
    Log { log: String },
    Done { done: String },
    Error { error: String },
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

    let (tx, mut rx) = mpsc::unbounded_channel::<ServerMessage>();

    loop {
        while let Ok(msg) = rx.try_recv() {
            match msg {
                ServerMessage::Log { log } => logs.push(log),
                ServerMessage::Done { done } => {
                    logs.push(format!("Done: {}", done));
                    status = Status::Done(done);
                }
                ServerMessage::Error { error } => {
                    logs.push(format!("Error: {}", error));
                    status = Status::Error(error);
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
                        let task2 = task.clone();
                        tokio::spawn(async move {
                            if let Err(e) = send_task(task2, tx2).await {
                                eprintln!("send_task error: {e}");
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

async fn send_task(task: String, tx: mpsc::UnboundedSender<ServerMessage>) -> io::Result<()> {
    let stream = TcpStream::connect("127.0.0.1:9000").await.map_err(|e| {
        let _ = tx.send(ServerMessage::Error {
            error: format!("Cannot connect to agent server: {e}. Is main.py running?"),
        });
        e
    })?;

    let (reader_half, mut writer_half) = stream.into_split();
    let request = serde_json::to_string(&Request { task }).unwrap() + "\n";
    writer_half.write_all(request.as_bytes()).await?;

    let mut lines = BufReader::new(reader_half).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        match serde_json::from_str::<ServerMessage>(&line) {
            Ok(msg) => {
                let _ = tx.send(msg);
            }
            Err(_) => {
                let _ = tx.send(ServerMessage::Log { log: line });
            }
        }
    }
    Ok(())
}
