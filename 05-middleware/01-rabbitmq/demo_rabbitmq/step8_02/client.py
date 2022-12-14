import pika, logging


class RabbitMQClient:
    def __init__(self):
        self.exchange_type = "direct"
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host="192.168.19.160"))
        self.channel = self.connection.channel()
        self._declare_retry_queue()  # RetryQueue and RetryExchange
        logging.debug("connection established")

    def close_connection(self):
        self.connection.close()
        logging.debug("connection closed")

    def declare_exchange(self, exchange):
        self.channel.exchange_declare(exchange=exchange,
                                      exchange_type=self.exchange_type,
                                      durable=True)

    def declare_queue(self, queue):
        self.channel.queue_declare(queue=queue,
                                   durable=True, )

    def declare_delay_queue(self, queue, DLX='RetryExchange', TTL=6000):
        """
        创建延迟队列
        :param TTL: ttl的单位是us，ttl=60000 表示 60s
        :param queue:
        :param DLX:死信转发的exchange
        :return:
        """
        arguments = {}
        if DLX:
            # 设置死信转发的exchange
            arguments['x-dead-letter-exchange'] = DLX
        if TTL:
            arguments['x-message-ttl'] = TTL
        print(arguments)
        self.channel.queue_declare(queue=queue,
                                   durable=True,
                                   arguments=arguments)

    def _declare_retry_queue(self):
        """
        创建异常交换器和队列，用于存放没有正常处理的消息。
        :return:
        """
        self.channel.exchange_declare(exchange='RetryExchange',
                                      exchange_type='fanout',
                                      durable=True)
        self.channel.queue_declare(queue='RetryQueue',
                                   durable=True)
        self.channel.queue_bind('RetryQueue', 'RetryExchange', 'RetryQueue')

    def publish_message(self, routing_key, msg, exchange='', delay=0, TTL=None):
        """
        发送消息到指定的交换器
        :param exchange: RabbitMQ交换器
        :param msg: 消息实体，是一个序列化的JSON字符串
        :return:
        """
        if delay == 0:
            self.declare_queue(routing_key)
        else:
            self.declare_delay_queue(routing_key, TTL=TTL)
        if exchange != '':
            self.declare_exchange(exchange)
        self.channel.basic_publish(exchange=exchange,
                                   routing_key=routing_key,
                                   body=msg,
                                   properties=pika.BasicProperties(
                                       delivery_mode=2,
                                       type=exchange
                                   ))
        self.close_connection()
        print("message send out to %s" % exchange)
        logging.debug("message send out to %s" % exchange)

    def start_consume(self, callback, queue='#', delay=1):
        """
        启动消费者，开始消费RabbitMQ中的消息
        :return:
        """
        if delay == 1:
            queue = 'RetryQueue'
        else:
            self.declare_queue(queue)
        self.channel.basic_qos(prefetch_count=1)
        try:
            self.channel.basic_consume(  # 消费消息
                queue=queue,  # 你要从那个队列里收消息
                on_message_callback=callback  # 如果收到消息，就调用callback函数来处理消息

            )
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.stop_consuming()

    def stop_consuming(self):
        self.channel.stop_consuming()
        self.close_connection()

    def message_handle_successfully(channel, method):
        """
        如果消息处理正常完成，必须调用此方法，
        否则RabbitMQ会认为消息处理不成功，重新将消息放回待执行队列中
        :param channel: 回调函数的channel参数
        :param method: 回调函数的method参数
        :return:
        """
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def message_handle_failed(channel, method):
        """
        如果消息处理失败，应该调用此方法，会自动将消息放入异常队列
        :param channel: 回调函数的channel参数
        :param method: 回调函数的method参数
        :return:
        """
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
