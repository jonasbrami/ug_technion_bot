import mechanicalsoup
import time
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          ConversationHandler)

TIME_BETWEEN_REQUESTS = 30
TIME_BETWEEN_POOLS = 300


def checker(courses, id, pwd):
    available_list = list()
    browser = mechanicalsoup.StatefulBrowser()
    browser.open("https://ug3.technion.ac.il/rishum/login")

    if browser.get_url() == 'https://ug3.technion.ac.il/rishum/no-service':
        return list()

    browser.select_form()
    browser.get_current_form()
    browser["UID"] = id
    browser["PWD"] = pwd
    browser.submit_selected()

    print(browser.get_url()) #for test
    if browser.get_url()!='https://ug3.technion.ac.il/rishum/cart':
        raise Exception("Wrong IDs")

    for course in courses:
        browser.open('https://ug3.technion.ac.il/rishum/vacancy/' + course)
        page = browser.get_current_page()
        isAvailable = not bool(page.find("div", class_="error-msg"))
        if isAvailable:
            print(page)
            available_list.append(course)
        time.sleep(TIME_BETWEEN_REQUESTS)
    return available_list


IDS, COURSES, POOL = range(3)


def start(bot, update):
    update.message.reply_text("Enter your ug's id and password separated by one space. Example:\n123456789 password")
    return IDS


def get_ids(bot, update, chat_data):
    chat_data['id'], chat_data['password'] = update.message.text.split()
    chat_data['chat_id'] = update.message.chat_id
    update.message.reply_text("Enter the course's number . Example:\n 11111 22222")
    return COURSES


def get_courses_and_pool(bot, update, chat_data, job_queue):
    chat_data['courses'] = update.message.text.split()
    update.message.reply_text("You will receive a notification as soon as a spot is available")
    update.message.reply_text("Pooling started! Send /cancel to stop")
    job = job_queue.run_repeating(pool, interval=TIME_BETWEEN_POOLS, first=0, context=chat_data)
    chat_data['job'] = job
    return POOL


def pool(bot, job):
    chat_data = job.context
    notification = ""
    try:
        available_list = checker(chat_data['courses'], chat_data['id'], chat_data['password'])
    except Exception as e:
        chat_data['job'].enabled=False
        bot.send_message(chat_id=chat_data['chat_id'], text="Wrong IDs, Job disabled, send /cancel and then /start to create a new one.")
        return

    for course in available_list:
        notification += "A spot is available for " + course + "\n"
        chat_data['courses'].remove(course)
    if notification != "":
        bot.send_message(chat_id=chat_data['chat_id'], text=notification)
    return

def job_already_running(bot, update,chat_data):
    if chat_data['job'].enabled == False:
        update.message.reply_text("No job running. Send /start to make a new one")
        return ConversationHandler.END

    update.message.reply_text(
        "A job is already running for "
        + ' '.join(chat_data['courses'])+'\n'
        + "To modify it, send /cancel to stop it and then /start to make a new one")
    return POOL

def cancel(bot, update, chat_data):
    chat_data['job'].schedule_removal()
    update.message.reply_text("Pooling Stopped! Send /start to create a new job")
    return ConversationHandler.END


updater = Updater(token='ENTER YOUR TOKEN HERE')

dispatcher = updater.dispatcher

ug_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={

        IDS: [MessageHandler(Filters.text, get_ids, pass_chat_data=True)],

        COURSES: [MessageHandler(Filters.text, get_courses_and_pool, pass_chat_data=True, pass_job_queue=True)],

        POOL: [MessageHandler(Filters.text, job_already_running, pass_chat_data=True)],
    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)]
)

dispatcher.add_handler(ug_handler)

updater.start_polling()
